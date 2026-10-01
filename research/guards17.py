import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import gold17_var as V
PREP = {}
GUARDS = {"5% / 2.5% daily (now)": (5.0, 2.5), "6% / 3%": (6.0, 3.0), "7% / 3.5%": (7.0, 3.5)}
def init():
    PREP["t"] = F.prepare(V.trades("base"))
def one(a):
    gname, hz, s = a; tot, day = GUARDS[gname]
    t, ev, days = PREP["t"]
    return gname, hz, s, F.run_challenge(t, ev, days, s, F.scaled(1.25, 4, 0.25, int_total=tot), horizon_days=hz, int_daily=day, int_total=tot)[0]
if __name__ == "__main__":
    starts = [s for s in pd.date_range("2010-06-01", "2026-06-01", freq="5D", tz=F.PRAGUE) if s.weekday() < 5]
    jobs = [(g, hz, s) for g in GUARDS for hz in (30, 90, 365) for s in starts if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-20", tz="UTC")]
    with Pool(14, initializer=init) as p:
        res = p.map(one, jobs, chunksize=30)
    d = pd.DataFrame(res, columns=["name", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-26"])
    d["pass"] = d.res == "pass"; d["stuck"] = d.res == "fail"
    pd.set_option("display.width", 300)
    print(pd.concat([d.pivot_table(index="name", columns="hz", values="pass", aggfunc="mean").add_prefix("pass"),
                     d.pivot_table(index="name", columns="hz", values="stuck", aggfunc="mean").add_prefix("stuck")], axis=1).round(3).to_string())
    print(d[d.hz == 365].pivot_table(index="name", columns="era", values="pass", aggfunc="mean").round(2).to_string())
