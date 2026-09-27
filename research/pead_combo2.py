"""FTMO odds: deployed gold + Nasdaq vs + post-earnings drift (k2.5, hold 10 days, confirm) on 44 US stock CFDs.
Stock entries at 09:30 NY on the entry date, exits at 09:30 NY on the exit date. Live risk policy. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from pead import trades as pead_trades, SYMS
from third_combo import gold_bad_at


def pead_book(k=2.5, N=10, confirm=True):
    t = pd.concat([pead_trades(s, k=k, N=N, confirm=confirm) for s in SYMS])
    ny = lambda x: (pd.to_datetime(x) + pd.Timedelta(hours=9, minutes=30)).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    t["entry_time"], t["exit_time"] = ny(t.entry_time), ny(t.exit_time)
    t["w"] = 1.0; t["stop"] = t.r < -0.9; t["mkt"] = "stocks"
    return t[(t.entry_time >= S.START)][["entry_time", "exit_time", "r", "w", "stop", "mkt"]]


PREP = {}
def init():
    base = S.book(); p = pead_book(); bad = gold_bad_at(p.entry_time)
    V = {"gold + Nasdaq (deployed)": base}
    for w in (0.25, 0.5):
        V[f"+ stock drift always, {w}x risk"] = pd.concat([base, p.assign(w=w)])
        V[f"+ stock drift gold-BAD only, {w}x risk"] = pd.concat([base, p[bad].assign(w=w)])
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
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "ranging 21-23", "trending 24-26")
    g = res.groupby("name")
    pd.set_option("display.width", 250)
    print(pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "avg 30d %": g.p30.mean(), "lowest vs start": g.low90.min(), "worst day": g.wd90.min()}).round(3).to_string())
    print(res.pivot_table(index="name", columns="era", values="pass60", aggfunc="mean").round(3).to_string())
