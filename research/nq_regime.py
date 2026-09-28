"""Nasdaq self-regime filter (same rule as gold's): paper record = every Nasdaq trade the EA would take (Fed days
skipped). BAD = trades closed in the last D days sum < 0 with >= 5 trades -> Nasdaq risk x M (0.5 / 0.25 / 0 = pause).
Combined with gold v2 (live policy). Neighbours: D 30/45/60/90, M 0.5/0.25/0. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from portfolio import nasdaq_all
from third_combo import gold_bad_at


def nq_bad(nq, days, min_trades=5):
    ex = nq.exit_time.values.astype("datetime64[ns]"); order = np.argsort(ex)
    ex, r = ex[order], nq.r.values[order]; cum = np.r_[0, np.cumsum(r)]
    e = nq.entry_time.values.astype("datetime64[ns]")
    hi = np.searchsorted(ex, e, side="left"); lo = np.searchsorted(ex, e - np.timedelta64(days, "D"))
    return (hi - lo >= min_trades) & (cum[hi] - cum[lo] < 0)


VARIANTS = {"LIVE NOW: no Nasdaq filter": None}
for D in (30, 45, 60, 90):
    for M in (0.5, 0.25, 0.0):
        VARIANTS[f"Nasdaq filter {D}d, BAD -> {M}x"] = (D, M)
PREP = {}


def init():
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    nq = nasdaq_all().reset_index(drop=True)
    for name, v in VARIANTS.items():
        w = np.full(len(nq), 0.75)
        if v is not None:
            w = np.where(nq_bad(nq, v[0]), 0.75 * v[1], 0.75)
        n = nq.assign(w=w); n = n[n.w > 0]
        t = pd.concat([g, n]).sort_values("entry_time").reset_index(drop=True)
        PREP[name] = (t,) + F.prepare(t)[1:]


def job(a):
    name, s = a; t, ev, days = PREP[name]
    out = dict(name=name, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"] = p, st
    return out


def month(a):
    name, s = a; t, ev, days = PREP[name]
    nxt = s + pd.offsets.MonthBegin(1)
    b, m, w, _, _, pnl, lo = S.sim(t, ev, days, s, (nxt - s).days)
    return dict(name=name, start=s, total=b, nasdaq=sum(x for k, x in pnl if k == "nasdaq"))


if __name__ == "__main__":
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(VARIANTS, S.STARTS[::2])), chunksize=30))
        mo = pd.DataFrame(p.map(month, list(itertools.product(VARIANTS, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    mo["y"] = mo.start.dt.year
    g = res.groupby("name", sort=False)
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "pass60 gold-BAD start": res[res.bad].groupby("name", sort=False).pass60.mean()})
    gm = mo.groupby("name", sort=False)
    tab["avg month %"] = gm.total.mean(); tab["months +"] = gm.total.apply(lambda v: (v > 0).mean())
    tab["worst month %"] = gm.total.min()
    ny = mo.pivot_table(index="name", columns="y", values="nasdaq", aggfunc="sum").reindex(tab.index)
    tab = tab.join(ny.add_prefix("NQ ").round(1))
    pd.set_option("display.width", 300)
    print(tab.round(3).to_string())
