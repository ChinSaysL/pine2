"""FTMO odds (with gold v2, live policy) for the Nasdaq logic candidates from nq_logic.py. Nasdaq trades are placed at
09:45 -> 15:55 NY (noise-area at 10:00 -> 15:55): conservative for overlapping open risk. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from third_combo import gold_bad_at


def book_from(series, w, start_hm=(9, 45)):
    d = pd.to_datetime(series.index)
    ent = (d + pd.Timedelta(hours=start_hm[0], minutes=start_hm[1])).tz_localize("America/New_York").tz_convert("UTC")
    ex = (d + pd.Timedelta(hours=15, minutes=55)).tz_localize("America/New_York").tz_convert("UTC")
    return pd.DataFrame({"entry_time": ent, "exit_time": ex, "r": series.values, "w": w, "stop": series.values < -0.5, "mkt": "nasdaq"})


PREP = {}
def init():
    R = pd.read_pickle("nq_logic.pkl")
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    base, l5, l2, l7 = R["BASE"], R["L5"], R["L2"], R["L7"]
    aligned = base.index.isin(l5.index)
    V = {"LIVE: current Nasdaq 0.75x": book_from(base, 0.75),
         "L5 gap-aligned only, 0.75x": book_from(l5, 0.75),
         "L5 gap-aligned only, 1.0x": book_from(l5, 1.0),
         "gap-aligned 1.0x / not aligned 0.5x": book_from(base, np.where(aligned, 1.0, 0.5)),
         "gap-aligned 0.75x / not aligned 0.375x": book_from(base, np.where(aligned, 0.75, 0.375)),
         "L2 stop-and-reverse, 0.75x": book_from(l2, 0.75),
         "current 0.75x + noise-area 0.5x": pd.concat([book_from(base, 0.75), book_from(l7, 0.5, (10, 0))])}
    for k, n in V.items():
        t = pd.concat([g, n]).sort_values("entry_time").reset_index(drop=True)
        PREP[k] = (t,) + F.prepare(t)[1:]


def job(a):
    name, s = a; t, ev, days = PREP[name]
    out = dict(name=name, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"wd{h}"] = p, st, w
    return out


def month(a):
    name, s = a; t, ev, days = PREP[name]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(name=name, start=s, pnl=b)


if __name__ == "__main__":
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(PREP, S.STARTS)), chunksize=30))
        mo = pd.DataFrame(p.map(month, list(itertools.product(PREP, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "21-23", "24-26")
    g = res.groupby("name", sort=False); gm = mo.groupby("name", sort=False)
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "pass60 21-23": res[res.era == "21-23"].groupby("name", sort=False).pass60.mean(),
                        "pass60 24-26": res[res.era == "24-26"].groupby("name", sort=False).pass60.mean(),
                        "pass60 gold-BAD start": res[res.bad].groupby("name", sort=False).pass60.mean(),
                        "avg month %": gm.pnl.mean(), "months +": gm.pnl.apply(lambda v: (v > 0).mean()),
                        "2026 months avg %": mo[mo.start >= pd.Timestamp("2026-01-01", tz="UTC")].groupby("name", sort=False).pnl.mean(),
                        "worst day": g.wd90.min()})
    pd.set_option("display.width", 300)
    print(tab.round(3).to_string())
