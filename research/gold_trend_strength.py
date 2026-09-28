"""Gold: half risk when the daily trend is only marginally established (yesterday's close within X% of its 50-day SMA,
just past the 1% neutral band). 17-year Python replica by era + FTMO challenge sim with the full live system. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from third_combo import gold_bad_at
from final_summary import book as live_book
from oldgold import load_full

XS = [0, 1.5, 2.0, 2.5, 3.0]                                   # 0 = live (no reduction)

def dist_series():
    g = load_full("XAUUSD", "data/XAUUSD_H1.csv")
    closes = g.groupby("tday").c.last(); sma = closes.rolling(50).mean()
    return (((closes - sma) / sma * 100).shift(1)).abs()

if __name__ == "__main__":
    t = pd.read_pickle("gold_diag.pkl")
    print("17-YEAR REPLICA: gold R by era (live weighting) when units with |dist| < X% get half risk")
    rows = []
    for X in XS:
        w = t.w * np.where(t.dist < X, 0.5, 1.0) if X else t.w
        r = (t.r * w).groupby(t.era).sum().round(1).to_dict(); r["X"] = X; r["total"] = round(float((t.r * w).sum()), 1); rows.append(r)
    print(pd.DataFrame(rows).set_index("X").to_string())

DIST = {}
PREP = {}
def init():
    ds = dist_series()
    lb = live_book(); gold = lb[lb.mkt == "gold"].copy(); rest = lb[lb.mkt != "gold"]
    ny = gold.entry_time.dt.tz_convert("America/New_York")
    gold["dist"] = ((ny + pd.Timedelta(hours=7)).dt.date).map(ds)
    for X in XS:
        g = gold.copy()
        if X: g["w"] = g.w * np.where(g.dist < X, 0.5, 1.0)
        b = pd.concat([g[rest.columns], rest]).sort_values("entry_time").reset_index(drop=True)
        PREP[X] = (b,) + F.prepare(b)[1:]
def job(a):
    X, s = a; t, ev, days = PREP[X]; out = dict(X=X, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"] = p, st
    return out
def month(a):
    X, s = a; t, ev, days = PREP[X]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(X=X, start=s, pnl=b)
if __name__ == "__main__":
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(XS, S.STARTS)), chunksize=40))
        mo = pd.DataFrame(p.map(month, list(itertools.product(XS, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC")); mo["y"] = mo.start.dt.tz_convert("Europe/Prague").dt.year
    g = res.groupby("X"); gm = mo.groupby("X")
    print("\nFULL LIVE SYSTEM (FTMO challenge sim, Oct 2021 - Sep 2026)")
    print(pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "p60 gold-BAD": res[res.bad].groupby("X").pass60.mean(), "avg month %": gm.pnl.mean(),
                        "2026 avg month": mo[mo.y == 2026].groupby("X").pnl.mean()}).round(3).to_string())
