"""FTMO challenge odds 2010-2026 for different BAD-regime behaviours of the gold strategy (Python replica)."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from regime import paper_trades, regime_flag
from oldgold import load_full

PREP = {}
def variants():
    g = load_full("XAUUSD", "data/XAUUSD_H1.csv")
    p = paper_trades(g); bad = regime_flag(g, p)
    ei = g.set_index("time").index.get_indexer(pd.DatetimeIndex(p.entry_time))
    nyh = g.ny_h.values[ei]; b = bad[ei]; ny = (nyh >= 8) & (nyh < 17)
    p = p[["entry_time", "exit_time", "r"]].copy()
    v = {"no filter": p.assign(w=1.0), "BAD: 0.25x risk": p.assign(w=np.where(b, 0.25, 1.0)), "BAD: 0.75x risk": p.assign(w=np.where(b, 0.75, 1.0)),
         "BAD: NY only (live)": p[~b | ny].assign(w=1.0),
         "BAD: pause": p[~b].assign(w=1.0),
         "BAD: half risk": p.assign(w=np.where(b, 0.5, 1.0)),
         "BAD: NY only, half risk": p[~b | ny].assign(w=np.where(b[~b | ny], 0.5, 1.0))}
    return v

def init():
    for k, t in variants().items():
        t = t.copy(); t["wcap"] = 99; PREP[k] = F.prepare(t)

def one(a):
    name, hz, s = a
    t, ev, days = PREP[name]
    return name, hz, s, F.run_challenge(t, ev, days, s, F.scaled(1.25, 4, 0.25, int_total=5.0), horizon_days=hz, int_daily=2.5, int_total=5.0)[0]

if __name__ == "__main__":
    init()
    starts = [s for s in pd.date_range("2010-06-01", "2026-06-01", freq="5D", tz=F.PRAGUE) if s.weekday() < 5]
    jobs = [(n, hz, s) for n in PREP for hz in (30, 90, 365) for s in starts if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-20", tz="UTC")]
    with Pool(14, initializer=init) as p:
        res = p.map(one, jobs, chunksize=30)
    d = pd.DataFrame(res, columns=["name", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-26"])
    d["pass"] = d.res == "pass"; d["stuck"] = d.res == "fail"
    pd.set_option("display.width", 300)
    print("PASS rate"); print(d.pivot_table(index="name", columns=["hz", "era"], values="pass", aggfunc="mean").round(2).to_string())
    print("\nPASS rate all eras"); print(d.pivot_table(index="name", columns="hz", values="pass", aggfunc="mean").round(3).to_string())
    print("\nSTUCK rate (90d)"); print(d[d.hz == 90].pivot_table(index="name", columns="era", values="stuck", aggfunc="mean").round(2).to_string())
    d.to_pickle("gold17_sim2.pkl")
    print("STUCK 365d"); print(d[d.hz == 365].pivot_table(index="name", columns="era", values="stuck", aggfunc="mean").round(2).to_string())
