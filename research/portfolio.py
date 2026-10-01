"""Regime-independent portfolio: every strategy always on with its own risk share, vs the deployed gating.
Live policy (cap 1.25%, divisor 4, guards 7% / 3.5%, gold BAD units 0.5x); w = strategy risk multiplier. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from pead_combo import pead_book


def nasdaq_all():
    t = pd.read_csv("mt5_nq_ftmo2.csv", sep=";")
    ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    t["entry_time"], t["exit_time"] = ny(t.entry_time_ny), ny(t.exit_time_ny)
    t = t.dropna(subset=["entry_time", "exit_time"])
    t["stop"] = t.r < -0.5; t["mkt"] = "nasdaq"
    from newfam import FOMC                                    # FTMO news rule: no Nasdaq trade on Fed decision days
    fomc = {pd.Timestamp(x).date() for x in FOMC}
    t = t[~t.entry_time.dt.tz_convert("America/New_York").dt.date.isin(fomc)]
    return t[["entry_time", "exit_time", "r", "stop", "mkt"]]


PREP = {}
def init():
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    nq = nasdaq_all()
    from third_combo import gold_bad_at
    bad = gold_bad_at(nq.entry_time)
    V = {"DEPLOYED: gold + Nasdaq only while gold BAD (FOMC days skipped)": pd.concat([g, nq[bad].assign(w=1.0)]),
         "gold alone": g}
    for wn in (0.5, 0.75, 1.0):
        V[f"gold + Nasdaq ALWAYS {wn}x (FOMC days skipped)"] = pd.concat([g, nq.assign(w=wn)])
    V["gold + Nasdaq: 1.0x while gold BAD, 0.5x while GOOD"] = pd.concat([g, nq.assign(w=np.where(bad, 1.0, 0.5))])
    for k, t in V.items():
        t = t.sort_values("entry_time").reset_index(drop=True)
        PREP[k] = (t,) + F.prepare(t)[1:]


def job(a):
    name, s = a; t, ev, days = PREP[name]
    out = dict(name=name, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"low{h}"], out[f"wd{h}"] = p, st, lo, w
    out["p30"] = S.sim(t, ev, days, s, 30)[0]
    return out


if __name__ == "__main__":
    init()
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(PREP, S.STARTS)), chunksize=20))
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "gold ranging 21-23", "gold trending 24-26")
    g = res.groupby("name")
    pd.set_option("display.width", 250)
    print(pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck60": g.stuck60.mean(),
                        "stuck90": g.stuck90.mean(), "avg 30d %": g.p30.mean(), "5% worst low (90d)": g.low90.quantile(.05),
                        "worst day": g.wd90.min()}).round(3).to_string())
    print("\npass within 60 days by era"); print(res.pivot_table(index="name", columns="era", values="pass60", aggfunc="mean").round(3).to_string())
    print("\npass within 30 days by era"); print(res.pivot_table(index="name", columns="era", values="pass30", aggfunc="mean").round(3).to_string())
