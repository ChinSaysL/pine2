"""Combine the two individually-robust improvements: stop-and-reverse (SAR) + noise-area engine. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from third_combo import gold_bad_at
import nq_v3 as V

VARS = {"current (live)": [("BASE", "orb", 0.75)],
        "SAR": [("SAR", None, 0.75)],
        "NOISE 0.75x": [("BASE", "orb", 0.75), ("BASE+NOISE", "noise", 0.75)],
        "SAR + NOISE 0.75x": [("SAR", None, 0.75), ("BASE+NOISE", "noise", 0.75)],
        "SAR + NOISE 0.5x": [("SAR", None, 0.75), ("BASE+NOISE", "noise", 0.5)],
        "SAR + NOISE 0.5x, all Nasdaq 0.6x": [("SAR", None, 0.6), ("BASE+NOISE", "noise", 0.5)]}
PREP = {}
def init():
    T = pd.read_pickle("nq_v3_trades.pkl")
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    for name, parts in VARS.items():
        bits = []
        for var, kind, w in parts:
            t = T[T.variant == var]
            if kind: t = t[t.kind == kind]
            bits.append(t.assign(w=w, stop=t.r < -0.5, mkt="nasdaq")[["entry_time", "exit_time", "r", "w", "stop", "mkt"]])
        b = pd.concat([g] + bits).sort_values("entry_time").reset_index(drop=True)
        PREP[name] = (b,) + F.prepare(b)[1:]
def job(a):
    v, s = a; t, ev, days = PREP[v]; out = dict(v=v, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"wd{h}"], out[f"low{h}"] = p, st, w, lo
    return out
def month(a):
    v, s = a; t, ev, days = PREP[v]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(v=v, start=s, pnl=b)
if __name__ == "__main__":
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(VARS, S.STARTS)), chunksize=30))
        mo = pd.DataFrame(p.map(month, list(itertools.product(VARS, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "21-23", "24-26")
    mo["y"] = mo.start.dt.year
    g = res.groupby("v", sort=False); gm = mo.groupby("v", sort=False)
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "p60 21-23": res[res.era == "21-23"].groupby("v", sort=False).pass60.mean(),
                        "p60 24-26": res[res.era == "24-26"].groupby("v", sort=False).pass60.mean(),
                        "p60 gold-BAD": res[res.bad].groupby("v", sort=False).pass60.mean(),
                        "avg month %": gm.pnl.mean(), "months +": gm.pnl.apply(lambda v: (v > 0).mean()), "worst month": gm.pnl.min(),
                        "worst day": g.wd90.min(), "lowest": g.low90.min()})
    pd.set_option("display.width", 300)
    print(tab.round(3).to_string())
    print(mo.pivot_table(index="v", columns="y", values="pnl", aggfunc="sum").round(1).reindex(list(VARS)).to_string())
