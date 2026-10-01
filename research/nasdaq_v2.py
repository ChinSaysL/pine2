"""Nasdaq-100 opening-range momentum: improvement grid, fixed before looking at results.

Data: dev = Dukascopy NDX minute bars -> M5, 2018-01..2021-08; holdout = FTMO US100.cash M5, 2021-09..2026-09.
Each day (09:30-16:00 NY): the first W minutes set the direction (close vs open) and the range; entry at the next
bar's open; stop at the range's opposite extreme with a floor of 0.3 x daily ATR; exits:
  eod  - close at the 15:55 bar
  vwap - close when a bar closes on the wrong side of the session VWAP (from 09:30), else 15:55
Filters: rvol - opening-window volume / its mean over the previous 14 days >= 1; doji - skip when the opening
window's body < 10% of its range. Cost = 1.45e-4 x price per round trip (~2 x FTMO spread). R per trade.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
COST_REL = 1.45e-4


def bars(source):
    if source == "dk":
        d = pd.read_csv(f"{DATA}\\DK_NDX_M1.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
        d = d.set_index("utc").resample("5min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
        d = d[d.utc < "2021-09-01"]
    else:
        d = pd.read_csv(f"{DATA}\\FT_US100.cash_M5.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
        d = d.rename(columns={"tick_volume": "volume"})
        d = d[d.utc >= "2021-09-01"]
    ny = d.utc.dt.tz_convert("America/New_York")
    d["date"], d["hm"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute
    d = d[(d.hm >= 570) & (d.hm < 960)].rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
    return d.reset_index(drop=True)


def days(d):
    out = {}
    for day, x in d.groupby("date"):
        if len(x) >= 70 and x.hm.iloc[0] == 570: out[day] = x.reset_index(drop=True)
    D = pd.DataFrame({k: dict(h=x.h.max(), l=x.l.min(), c=x.c.iloc[-1]) for k, x in out.items()}).T.astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    return out, D


def run(dd, D, W=15, exit="eod", rvol=False, doji=False, floor=0.3):
    k = W // 5
    keys = list(dd.keys())
    ovol = pd.Series({t: dd[t].v.iloc[:k].sum() for t in keys})
    ovol_avg = ovol.rolling(14).mean().shift(1)
    out = []
    for t in keys:
        x = dd[t]; a = D.atr[t]
        if np.isnan(a): continue
        first = x.iloc[:k]
        o0, c0, hi, lo = first.o.iloc[0], first.c.iloc[-1], first.h.max(), first.l.min()
        if c0 == o0 or hi == lo: continue
        if doji and abs(c0 - o0) < 0.1 * (hi - lo): continue
        if rvol and (np.isnan(ovol_avg[t]) or ovol_avg[t] <= 0 or ovol[t] < ovol_avg[t]): continue
        dr = 1 if c0 > o0 else -1
        rest = x.iloc[k:]
        e = rest.o.iloc[0]
        st = lo if dr == 1 else hi
        if (e - st) * dr < floor * a: st = e - dr * floor * a
        risk = (e - st) * dr
        if risk <= 0: continue
        if exit == "vwap":
            vv = x.v.replace(0, np.nan).fillna(1.0)
            tp = (x.h + x.l + x.c) / 3
            vwap = (tp * vv).cumsum() / vv.cumsum()
        px = None
        for i in range(k, len(x)):
            b = x.iloc[i]
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = min(b.o, st) if dr == 1 else max(b.o, st); break
            if b.hm >= 955: px = b.c; break
            if exit == "vwap" and i > k and (b.c - vwap.iloc[i]) * dr < 0: px = b.c; break
        if px is None: px = x.c.iloc[-1]
        out.append(dict(date=t, r=((px - e) * dr - COST_REL * e) / risk))
    return pd.DataFrame(out)


GRID = list(itertools.product([5, 15, 30], ["eod", "vwap"], [False, True], [False, True]))
CACHE = {}


def job(a):
    src, (W, ex, rv, dj) = a
    if src not in CACHE: CACHE[src] = days(bars(src))
    dd, D = CACHE[src]
    t = run(dd, D, W, ex, rv, dj)
    return src, W, ex, rv, dj, t


if __name__ == "__main__":
    jobs = [(s, g) for s in ("dk", "ft") for g in GRID]
    with Pool(14) as p:
        res = p.map(job, jobs, chunksize=3)
    rows = {}
    allt = []
    for src, W, ex, rv, dj, t in res:
        key = (W, ex, "rvol" if rv else "-", "doji" if dj else "-")
        pf = t.r[t.r > 0].sum() / max(-t.r[t.r < 0].sum(), 1e-9)
        yrs = pd.Series([x.year for x in t.date])
        rows.setdefault(key, {})[f"{'DEV dk 18-21' if src == 'dk' else 'HOLD ftmo 21-26'}"] = f"{t.r.sum():+6.1f}R n={len(t):4d} PF={pf:4.2f} R/yr={t.r.sum() / max(yrs.nunique(), 1):+5.1f}"
        t = t.assign(src=src, W=W, exit=ex, rvol=rv, doji=dj); allt.append(t)
    pd.concat(allt).to_pickle("nasdaq_v2.pkl")
    tab = pd.DataFrame(rows).T
    tab.index.names = ["W", "exit", "rvol", "doji"]
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
    print(tab.to_string())
