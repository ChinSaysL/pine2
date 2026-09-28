"""Noise-engine variant x risk split, full system FTMO odds (gold EA FTMO trades + Nasdaq opening EA trades + noise). 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from third_combo import gold_bad_at
import nq_noise2 as N
from final_summary import book as live_book

NV = {"BASE": {}, "CONF1+HOLD": dict(confirm=True, confirm_n=1, exit_mode="hold"), "CONF2+HOLD": dict(confirm=True, confirm_n=2, exit_mode="hold")}
GRID = [("BASE", 0.75, 0.75), ("CONF1+HOLD", 0.75, 0.75), ("CONF2+HOLD", 0.75, 0.75),
        ("CONF1+HOLD", 0.75, 0.5), ("CONF1+HOLD", 0.75, 1.0), ("CONF1+HOLD", 1.0, 0.75), ("CONF1+HOLD", 1.0, 0.5), ("BASE", 1.0, 0.75)]
def build(n):
    Ss, keys, D, cost = N.sessions(); t = N.run(Ss, keys, D, cost, **NV[n]); t["nv"] = n; return t
PREP = {}
def init():
    T = pd.read_pickle("nq_noise_sys_trades.pkl")
    lb = live_book(); gold = lb[lb.mkt == "gold"]; orb = lb[lb.mkt == "nasdaq opening"]
    for nv, wo, wn in GRID:
        n = T[T.nv == nv].assign(w=wn, stop=lambda x: x.r < -0.5, mkt="nasdaq noise")[["entry_time", "exit_time", "r", "w", "stop", "mkt"]]
        b = pd.concat([gold, orb.assign(w=wo), n]).sort_values("entry_time").reset_index(drop=True)
        PREP[(nv, wo, wn)] = (b,) + F.prepare(b)[1:]
def job(a):
    key, s = a; t, ev, days = PREP[key]; out = dict(key=f"{key[0]} | opening {key[1]}x | noise {key[2]}x", start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"wd{h}"], out[f"low{h}"] = p, st, w, lo
    return out
def month(a):
    key, s = a; t, ev, days = PREP[key]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(key=f"{key[0]} | opening {key[1]}x | noise {key[2]}x", start=s, pnl=b)
if __name__ == "__main__":
    with Pool(3) as p: T = pd.concat(p.map(build, list(NV)))
    T.to_pickle("nq_noise_sys_trades.pkl")
    T["era"] = np.select([T.day < pd.Timestamp("2024-01-01").date(), T.day < pd.Timestamp("2026-01-01").date()], ["2021-23", "2024-25"], "2026")
    print("NOISE variants R by era:"); print(T.groupby(["nv", "era"]).r.sum().unstack("era").round(1).assign(total=T.groupby("nv").r.sum().round(1), n=T.groupby("nv").size()).to_string())
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(GRID, S.STARTS)), chunksize=40))
        mo = pd.DataFrame(p.map(month, list(itertools.product(GRID, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC")); mo["y"] = mo.start.dt.tz_convert("Europe/Prague").dt.year
    order = list(dict.fromkeys(res.key))
    g = res.groupby("key"); gm = mo.groupby("key")
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "p30 gold-BAD": res[res.bad].groupby("key").pass30.mean(), "p60 gold-BAD": res[res.bad].groupby("key").pass60.mean(),
                        "avg month %": gm.pnl.mean(), "2026 avg month": mo[mo.y == 2026].groupby("key").pnl.mean(),
                        "2026 months +": mo[mo.y == 2026].groupby("key").pnl.apply(lambda v: (v > 0).mean()),
                        "worst day": g.wd90.min(), "lowest": g.low90.min()}).reindex(order)
    pd.set_option("display.width", 300); print(tab.round(3).to_string())
