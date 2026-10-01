"""Gold noise-area engine (FTMO XAUUSD M5, 2015-2026). Rules fixed in advance.
Anchor = session open (COMEX 08:20 NY or London 03:00 NY); band at each 5-min step = max/min(anchor open, previous
session close) +- the average |price/anchor open - 1| at the same step over the last 14 sessions. Every 30 min
(entry window: COMEX 09:00-15:30, London 03:30-15:30), a close outside the band opens one trade that day; hard stop at
the band or VWAP (farther, >= 0.3 daily ATR); exit when a 30-min check is back inside the band / across VWAP, or at
16:50 NY. News rule: no position 30 min before -> 30 min after listed releases (CPI / jobs 08:30, FOMC 14:00; dates:
FOMC 2018+, CPI/jobs 2021+, jobs = first Friday before 2021; CPI before 2021 unknown -> slightly optimistic then).
Also a CONFIRM+HOLD variant (entry only if still outside at the next check; hold to 16:50). Cost $0.30/oz. R per trade."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
from newfam import FOMC

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
COST = 0.30


def news_times():
    ev = [pd.Timestamp(f"{x} 14:00") for x in FOMC]
    for line in open("news_history_2021_2026.txt"):
        ev.append(pd.Timestamp(line.strip()))
    for m in pd.date_range("2015-01-01", "2020-12-31", freq="MS"):
        d = m + pd.offsets.Week(weekday=4) if m.weekday() != 4 else m
        ev.append(pd.Timestamp(f"{d.date()} 08:30"))
    return sorted(set(ev))                                     # New York wall-clock


def sessions(anchor_hm):
    d = pd.read_csv(f"{DATA}\\FT_XAUUSD_M5.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    ny = d.utc.dt.tz_convert("America/New_York")
    d["date"], d["hm"], d["nyt"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute, ny.dt.tz_localize(None)
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "tick_volume": "v"})
    s = d[(d.hm >= anchor_hm) & (d.hm < 1010)]                 # anchor .. 16:45 bar (flat 16:50)
    S = {k: x.reset_index(drop=True) for k, x in s.groupby("date") if x.hm.iat[0] == anchor_hm}
    keys = list(S)
    full_len = int(pd.Series([len(S[k]) for k in keys]).mode().iat[0])
    # daily ATR from full trading days (17:00 roll)
    d["tday"] = (ny + pd.Timedelta(hours=7)).dt.date
    g = d.groupby("tday"); DD = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    tr = np.maximum(DD.h - DD.l, np.maximum((DD.h - DD.c.shift()).abs(), (DD.l - DD.c.shift()).abs()))
    datr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    return S, keys, full_len, datr


def run(anchor_hm, first_entry, confirm=False, hold=False):
    S, keys, L0, datr = sessions(anchor_hm); NEWS = news_times()
    news_by_day = {}
    for t in NEWS: news_by_day.setdefault(t.date(), []).append(t.hour * 60 + t.minute)
    full = [k for k in keys if len(S[k]) >= L0]
    out = []
    for i, day in enumerate(keys):
        x = S[day]; L = len(x)
        if L < L0 - 2: continue
        hist = [k for k in full if k < day][-14:]
        if len(hist) < 10 or i == 0: continue
        prev = S[keys[i - 1]]; pc = prev.c.iat[-1]; a = datr.get(day, np.nan)
        if np.isnan(a): continue
        mv = np.array([np.abs(S[k].c.values[:L] / S[k].o.iat[0] - 1) for k in hist if len(S[k]) >= L])
        if len(mv) < 10: continue
        sig = mv.mean(axis=0); o = x.o.iat[0]
        ub = max(o, pc) * (1 + sig); lb = min(o, pc) * (1 - sig)
        tp = (x.h + x.l + x.c) / 3; vv = x.v.replace(0, 1); vwap = ((tp * vv).cumsum() / vv.cumsum()).values
        hm, c = x.hm.values, x.c.values
        nws = news_by_day.get(day, [])
        blocked = lambda m: any(n - 30 <= m + 5 and m <= n + 30 for n in nws)   # a bar overlapping a news window
        k = 0
        while k < L - 1:
            end = hm[k] + 5
            if not (end >= first_entry and (end - anchor_hm) % 30 == 0 and end <= 930) or blocked(hm[k]) or blocked(hm[k] + 5):
                k += 1; continue
            dr = 1 if c[k] > ub[k] else (-1 if c[k] < lb[k] else 0)
            if not dr: k += 1; continue
            if confirm:
                k2 = k + 6
                if k2 >= L - 1 or hm[k2] + 5 > 930 or not ((dr == 1 and c[k2] > ub[k2]) or (dr == -1 and c[k2] < lb[k2])): k += 1; continue
                k = k2
            e = x.o.iat[k + 1]
            st = min(ub[k], vwap[k]) if dr == 1 else max(lb[k], vwap[k])
            if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
            R = (e - st) * dr; px = None
            for j in range(k + 1, L):
                b = x.iloc[j]
                if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = min(b.o, st) if dr == 1 else max(b.o, st); break
                if blocked(hm[j] + 5): px = b.c; break                           # flat before a release
                trail = max(ub[j], vwap[j]) if dr == 1 else min(lb[j], vwap[j])
                chk = (hm[j] + 5 - anchor_hm) % 30 == 0
                if (not hold and chk and (c[j] - trail) * dr < 0) or hm[j] + 5 >= 1010: px = b.c; break
            if px is None: px = c[-1]; j = L - 1
            out.append(dict(day=day, entry_time=x.utc.iat[k + 1], exit_time=x.utc.iat[j] + pd.Timedelta(minutes=5),
                            r=((px - e) * dr - COST) / R, dir=dr))
            break
    return pd.DataFrame(out)


VARS = {"COMEX 08:20 anchor": dict(anchor_hm=500, first_entry=540), "COMEX 08:20 CONFIRM+HOLD": dict(anchor_hm=500, first_entry=540, confirm=True, hold=True),
        "London 03:00 anchor": dict(anchor_hm=180, first_entry=210), "London 03:00 CONFIRM+HOLD": dict(anchor_hm=180, first_entry=210, confirm=True, hold=True)}


def job(n):
    t = run(**VARS[n]); t["v"] = n; return t


if __name__ == "__main__":
    with Pool(4) as p: T = pd.concat(p.map(job, list(VARS)))
    T["day"] = pd.to_datetime(T.day)
    T["era"] = pd.cut(T.day.dt.year, [2014, 2020, 2023, 2025, 2026], labels=["2015-20", "2021-23", "2024-25", "2026"])
    T.to_pickle("gold_noise.pkl")
    rows = []
    for v, t in T.groupby("v", sort=False):
        row = {"variant": v}
        for e, x in t.groupby("era"): row[e] = f"{x.r.sum():+6.1f}R n={len(x):4d} avg {x.r.mean():+.3f}"
        row["total"] = round(t.r.sum(), 1); row["PF"] = round(t.r[t.r > 0].sum() / -t.r[t.r < 0].sum(), 2)
        yr = t.groupby(t.day.dt.year).r.sum(); row["years +"] = f"{(yr > 0).sum()}/{len(yr)}"
        rows.append(row)
    pd.set_option("display.width", 260); print(pd.DataFrame(rows).to_string(index=False))
