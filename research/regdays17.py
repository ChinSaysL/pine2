import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from regime import paper_trades, regime_flag
from oldgold import load_full
PREP = {}
def init():
    g = load_full("XAUUSD", "data/XAUUSD_H1.csv"); p = paper_trades(g)
    ei = g.set_index("time").index.get_indexer(pd.DatetimeIndex(p.entry_time))
    for days in (30, 45, 60, 90):
        bad = regime_flag(g, p, days=days)[ei]
        t = p[["entry_time", "exit_time", "r"]].assign(w=np.where(bad, 0.5, 1.0), wcap=99)
        PREP[days] = F.prepare(t)
def one(a):
    k, hz, s = a; t, ev, days = PREP[k]
    return k, hz, s, F.run_challenge(t, ev, days, s, F.scaled(1.25, 4, 0.25, int_total=5.0), horizon_days=hz, int_daily=2.5, int_total=5.0)[0]
if __name__ == "__main__":
    starts = [s for s in pd.date_range("2010-06-01", "2026-06-01", freq="5D", tz=F.PRAGUE) if s.weekday() < 5]
    jobs = [(k, hz, s) for k in (30, 45, 60, 90) for hz in (30, 90, 365) for s in starts if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-20", tz="UTC")]
    with Pool(12, initializer=init) as p:
        res = p.map(one, jobs, chunksize=30)
    d = pd.DataFrame(res, columns=["days", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-26"])
    d["pass"] = d.res == "pass"; d["stuck"] = d.res == "fail"
    pd.set_option("display.width", 300)
    print(pd.concat([d.pivot_table(index="days", columns="hz", values="pass", aggfunc="mean").add_prefix("pass"),
                     d.pivot_table(index="days", columns="hz", values="stuck", aggfunc="mean").add_prefix("stuck")], axis=1).round(3).to_string())
    print(d[d.hz == 90].pivot_table(index="days", columns="era", values="pass", aggfunc="mean").round(2).to_string())
