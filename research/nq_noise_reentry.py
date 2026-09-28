"""Re-entry neighbours (1 / 2 / 3 / 5 noise trades a day) and FTMO odds of the full system with each. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from third_combo import gold_bad_at
import nq_noise2 as N
from final_summary import book as live_book

MT = [1, 2, 3, 5]
def build(m):
    Ss, keys, D, cost = N.sessions(); t = N.run(Ss, keys, D, cost, max_trades=m); t["m"] = m; return t
PREP = {}
def init():
    T = pd.read_pickle("nq_reentry_trades.pkl")
    base = live_book(); base = base[base.mkt != "nasdaq noise"]             # gold + Nasdaq opening (EA trades)
    for m in MT:
        n = T[T.m == m].assign(w=0.75, stop=lambda x: x.r < -0.5, mkt="nasdaq noise")[["entry_time", "exit_time", "r", "w", "stop", "mkt"]]
        b = pd.concat([base, n]).sort_values("entry_time").reset_index(drop=True)
        PREP[m] = (b,) + F.prepare(b)[1:]
def job(a):
    m, s = a; t, ev, days = PREP[m]; out = dict(m=m, start=s)
    for h in (30, 60, 90):
        b, mm, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"wd{h}"] = p, st, w
    return out
def month(a):
    m, s = a; t, ev, days = PREP[m]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(m=m, start=s, pnl=b)
if __name__ == "__main__":
    with Pool(4) as p: T = pd.concat(p.map(build, MT))
    T.to_pickle("nq_reentry_trades.pkl")
    T["era"] = np.select([T.day < pd.Timestamp("2024-01-01").date(), T.day < pd.Timestamp("2026-01-01").date()], ["2021-23", "2024-25"], "2026")
    print("NOISE ENGINE R by era (Python, each trade 1R):")
    print(T.groupby(["m", "era"]).r.sum().unstack("era").round(1).assign(total=T.groupby("m").r.sum().round(1), trades=T.groupby("m").size()).to_string())
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(MT, S.STARTS)), chunksize=30))
        mo = pd.DataFrame(p.map(month, list(itertools.product(MT, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC")); mo["y"] = mo.start.dt.tz_convert("Europe/Prague").dt.year
    g = res.groupby("m"); gm = mo.groupby("m")
    print("\nFULL SYSTEM (gold + Nasdaq opening + noise engine with up to m trades/day), FTMO challenge sim")
    print(pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "p60 gold-BAD": res[res.bad].groupby("m").pass60.mean(), "avg month %": gm.pnl.mean(),
                        "2026 avg month %": mo[mo.y == 2026].groupby("m").pnl.mean(), "2026 months +": mo[mo.y == 2026].groupby("m").pnl.apply(lambda v: (v > 0).mean()),
                        "worst day": g.wd90.min()}).round(3).to_string())
