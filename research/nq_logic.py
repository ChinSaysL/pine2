"""Nasdaq ORB logic changes (FTMO US100.cash M5, 2021-09..2026-09, Fed days + US holidays skipped). Fixed in advance.
BASE  first 15 min (3 x M5) sets direction; entry next bar; stop at the range's other side (floor 0.3 cash ATR); exit 15:55.
L1 add at +1R: a second unit at entry + 1R, both stops to breakeven (unit risk = entry2 - breakeven).
L2 stop-and-reverse once: stopped before 12:00 -> enter the other way at the stop, stop at the range's other side
   (floor 0.3 ATR), exit 15:55.
L3 skip monthly options-expiration Fridays (3rd Friday).
L4 only when the direction agrees with the 20-day trend (previous close vs its 20-day average).
L5 only when the direction agrees with the overnight gap (09:30 open vs the previous 16:00 close).
L6 time stop: at 12:00, close if the trade is below entry.
L7 noise-area momentum (Zarattini, Barbon & Aziz 2024): sigma(t) = 14-day mean |price(t)/open - 1| at that time of day;
   bounds = max/min(open, prev close) x (1 +- sigma); checked every 30 min from 10:00: above -> long, below -> short;
   exit when price is back inside the bound or across VWAP (checked every 30 min), or 15:55; one trade a day.
R per trade (L1 counts both units in R of the first unit's risk). Cost 2 x median spread per unit."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
from newfam import FOMC

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
FOMC_D = {pd.Timestamp(x).date() for x in FOMC}


def load():
    d = pd.read_csv(f"{DATA}\\FT_US100.cash_M5.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d[d.utc >= "2021-09-01"]
    ny = d.utc.dt.tz_convert("America/New_York")
    d["date"], d["hm"], d["wd"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute, ny.dt.weekday
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == 'US100.cash' and tf == 'M5'").iloc[0]
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "tick_volume": "v"})
    cash = d[(d.hm >= 570) & (d.hm < 960)]
    days = {k: x.reset_index(drop=True) for k, x in cash.groupby("date") if x.hm.iat[0] == 570 and len(x) >= 70 and k not in FOMC_D}
    D = pd.DataFrame({k: dict(o=x.o.iat[0], h=x.h.max(), l=x.l.min(), c=x.c.iat[-1]) for k, x in days.items()}).T.astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    D["pc"] = D.c.shift(1); D["sma20"] = D.c.rolling(20).mean().shift(1)
    return days, D, 2 * meta.spread_med * 0.01


def third_friday(day):
    t = pd.Timestamp(day)
    return t.weekday() == 4 and 15 <= t.day <= 21


def base_trade(x, D, day, cost, mode):
    a = D.atr[day]
    if np.isnan(a): return None
    f = x.iloc[:3]; o0, c0, hi, lo = f.o.iat[0], f.c.iat[-1], f.h.max(), f.l.min()
    if c0 == o0: return None
    dr = 1 if c0 > o0 else -1
    if mode == "L3" and third_friday(day): return None
    if mode == "L4" and (np.isnan(D.sma20[day]) or np.sign(D.pc[day] - D.sma20[day]) != dr): return None
    if mode == "L5" and (np.isnan(D.pc[day]) or np.sign(o0 - D.pc[day]) != dr): return None
    rest = x.iloc[3:]; e = rest.o.iat[0]
    st = lo if dr == 1 else hi
    if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
    R = (e - st) * dr
    total = 0.0; units = [(e, st)]; added = False; stop = st
    for b in rest.itertuples():
        # stop (all units)
        if (dr == 1 and b.l <= stop) or (dr == -1 and b.h >= stop):
            total += sum((stop - ue) * dr - cost for ue, _ in units)
            if mode == "L2" and b.hm < 720 and not added:
                e2 = stop; st2 = hi if dr == 1 else lo
                if (st2 - e2) * -dr < 0.3 * a: st2 = e2 + dr * 0.3 * a
                sub = rest[rest.utc > b.utc]
                px = None
                for c in sub.itertuples():
                    if (-dr == 1 and c.l <= st2) or (-dr == -1 and c.h >= st2): px = st2; break
                    if c.hm >= 955: px = c.c; break
                if px is None and len(sub): px = sub.c.iat[-1]
                if px is not None: total += ((px - e2) * -dr - cost) * (R / abs(e2 - st2))   # sized to the same 1R
            return total / R
        if mode == "L1" and not added and ((dr == 1 and b.h >= e + R) or (dr == -1 and b.l <= e - R)):
            added = True; stop = e; units.append((e + dr * R, e))
        if mode == "L6" and b.hm >= 720 and (b.c - e) * dr < 0:
            return sum((b.c - ue) * dr - cost for ue, _ in units) / R
        if b.hm >= 955:
            return sum((b.c - ue) * dr - cost for ue, _ in units) / R
    return sum((rest.c.iat[-1] - ue) * dr - cost for ue, _ in units) / R


def noise_area(days, D, cost):
    keys = list(days); out = {}
    move = {k: (x.c / x.o.iat[0] - 1).abs().values for k, x in days.items()}
    for i, day in enumerate(keys):
        if i < 14: continue
        x = days[day]; pc = D.pc[day]
        if np.isnan(pc): continue
        hist = [move[keys[j]] for j in range(i - 14, i) if len(move[keys[j]]) == len(x)]
        if len(hist) < 10: continue
        sig = np.mean(hist, axis=0)
        o = x.o.iat[0]; ub = max(o, pc) * (1 + sig); lb = min(o, pc) * (1 - sig)
        tp = (x.h + x.l + x.c) / 3; vv = x.v.replace(0, 1); vwap = ((tp * vv).cumsum() / vv.cumsum()).values
        pos = 0; e = None; risk = None; res = None
        for k in range(len(x)):
            hm = x.hm.iat[k]; c = x.c.iat[k]
            check = hm >= 595 and (hm + 5) % 30 == 0            # bar ending on :00 / :30 from 10:00
            if pos == 0 and check and hm < 900:
                if c > ub[k]: pos, e = 1, c
                elif c < lb[k]: pos, e = -1, c
                if pos: risk = max(abs(e - (ub[k] if pos == 1 else lb[k])), abs(e - vwap[k]), 0.3 * D.atr[day] if not np.isnan(D.atr[day]) else 0)
                continue
            if pos != 0:
                trail = max(ub[k], vwap[k]) if pos == 1 else min(lb[k], vwap[k])
                if (check and (c - trail) * pos < 0) or hm >= 955:
                    res = ((c - e) * pos - cost) / risk; break
        if res is not None: out[day] = res
    return out


def job(mode):
    days, D, cost = load()
    if mode == "L7":
        r = noise_area(days, D, cost)
    else:
        r = {}
        for day, x in days.items():
            v = base_trade(x, D, day, cost, mode)
            if v is not None: r[day] = v
    return mode, pd.Series(r)


LAB = {"BASE": "BASE (live)", "L1": "L1 add at +1R, breakeven", "L2": "L2 stop-and-reverse once (before 12:00)",
       "L3": "L3 skip monthly opex Fridays", "L4": "L4 only with 20-day trend", "L5": "L5 only with overnight gap",
       "L6": "L6 time stop 12:00 if losing", "L7": "L7 noise-area momentum (alternative engine)"}

if __name__ == "__main__":
    with Pool(14) as p:
        res = dict(p.map(job, list(LAB)))
    rows = []
    for m, s in res.items():
        s.index = pd.to_datetime(s.index)
        row = {"variant": LAB[m]}
        for p_, a, b in [("dev 2021-09..2023", "2021-01-01", "2024-01-01"), ("hold 2024-2026", "2024-01-01", "2027-01-01"), ("2026 only", "2026-01-01", "2027-01-01")]:
            x = s[(s.index >= a) & (s.index < b)]
            pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
            row[p_] = f"{x.sum():+7.1f}R n={len(x):4d} PF={pf:4.2f}"
        yr = s.groupby(s.index.year).sum(); row["years +"] = f"{(yr > 0).sum()}/{len(yr)}"
        rows.append(row)
    pd.to_pickle(res, "nq_logic.pkl")
    pd.set_option("display.width", 260)
    print(pd.DataFrame(rows).to_string(index=False))
