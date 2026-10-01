"""Evaluate real-EA tester exports: yearly %, max drawdown, worst Prague day, and FTMO challenge odds
(each trade replayed at the risk % the EA actually used, re-scaled by the challenge's own risk scheme)."""
import sys, warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
NAMES = sys.argv[1:] or ["nyonly", "halfrisk", "nofilter"]
def load(k):
    t = pd.read_csv(f"mt5_bm_{k}.csv", sep=";")
    ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    t["entry_time"], t["exit_time"] = ny(t.entry_time_ny), ny(t.exit_time_ny)
    t = t.dropna(subset=["entry_time", "exit_time"]).sort_values("exit_time").reset_index(drop=True)
    t["bal_after"] = 10000 + t.profit.cumsum(); t["bal_before"] = t.bal_after - t.profit
    t["pct"] = 100 * t.profit / 10000            # % of the initial balance (the EA and FTMO both measure against it)
    t["w"] = (100 * t.risk_usd / 10000) / 1.25; t["wcap"] = 99
    return t
PREP = {}
def init():
    for k in NAMES: PREP[k] = F.prepare(load(k)[["entry_time", "exit_time", "r", "w", "wcap"]])
def one(a):
    k, hz, s = a; t, ev, days = PREP[k]
    return k, hz, s, F.run_challenge(t, ev, days, s, F.scaled(1.25, 4, 0.25, int_total=5.0), horizon_days=hz, int_daily=2.5, int_total=5.0)[0]
if __name__ == "__main__":
    rows = {}
    for k in NAMES:
        t = load(k); eq = t.bal_after
        dd = ((eq.cummax() - eq) / 10000).max() * 100   # peak-to-trough in % of the initial balance
        day = t.groupby(t.exit_time.dt.tz_convert("Europe/Prague").dt.date).pct.sum()
        yr = t.groupby(t.exit_time.dt.year).pct.sum().round(1)
        rows[k] = dict(yr.to_dict(), maxDD_pct=round(dd, 1), worst_day_pct=round(day.min(), 2), trades=len(t))
    pd.set_option("display.width", 300)
    print(pd.DataFrame(rows).T.to_string())
    starts = [s for s in pd.date_range("2010-06-15", "2026-06-01", freq="5D", tz=F.PRAGUE) if s.weekday() < 5]
    jobs = [(k, hz, s) for k in NAMES for hz in (30, 90, 365) for s in starts if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-15", tz="UTC")]
    with Pool(14, initializer=init) as p:
        res = p.map(one, jobs, chunksize=30)
    d = pd.DataFrame(res, columns=["name", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-26"])
    d["pass"] = d.res == "pass"; d["stuck"] = d.res == "fail"
    print(pd.concat([d.pivot_table(index="name", columns="hz", values="pass", aggfunc="mean").add_prefix("pass"),
                     d.pivot_table(index="name", columns="hz", values="stuck", aggfunc="mean").add_prefix("stuck")], axis=1).round(3).to_string())
    print(d[d.hz == 90].pivot_table(index="name", columns="era", values="pass", aggfunc="mean").round(2).to_string())
    print(d[d.hz == 90].pivot_table(index="name", columns="era", values="stuck", aggfunc="mean").round(2).to_string())
