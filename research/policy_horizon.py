"""Pass / stuck / breach by horizon (30..365 days) for the live policy vs challenge v2 candidates. 14 workers."""
import itertools, warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import pandas as pd
import ftmo_sim2 as F
from policy_grid import trades, run

POL = {"live 1.25%/5%": (1.25, 4, 5.0), "v2 1.5%/7%": (1.5, 4, 7.0), "1.25%/7%": (1.25, 4, 7.0), "1.25%/6%": (1.25, 4, 6.0), "1.0%/7%": (1.0, 4, 7.0)}
STARTS = [s for s in pd.date_range("2010-09-01", "2025-09-01", freq="4D", tz=F.PRAGUE) if s.weekday() < 5]
PREP = {}
def init(): PREP["x"] = F.prepare(trades())
def job(a):
    name, hz = a; cap, div, T = POL[name]; t, ev, days = PREP["x"]
    return [(name, hz, s, run(t, ev, days, s, cap, div, T, T / 2, hz, 0.0)) for s in STARTS
            if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-15", tz="UTC")]

if __name__ == "__main__":
    with Pool(14, initializer=init) as p:
        res = [r for c in p.imap_unordered(job, list(itertools.product(POL, (30, 60, 90, 180, 365)))) for r in c]
    d = pd.DataFrame(res, columns=["name", "hz", "start", "res"])
    pd.set_option("display.width", 250)
    for k in ("pass", "stuck"):
        print(k.upper()); print(d.pivot_table(index="name", columns="hz", values="res", aggfunc=lambda x: (x == k).mean()).round(3).to_string())
