"""FTMO challenge odds: gold (live rules incl. regime filter) alone vs + USDJPY breakout. Live risk scheme."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import pyramid, ftmo_sim2 as F
from regime import load_mt5, paper_trades, regime_flag
from multi import load_sym, trend_atr

def gold_trades():
    g = load_mt5("H1"); p = paper_trades(g); bad = regime_flag(g, p)
    ei = g.set_index("time").index.get_indexer(pd.DatetimeIndex(p.entry_time))
    nyh = g.ny_h.values[ei]
    live = p[~bad[ei] | ((nyh >= 8) & (nyh < 17))].copy()
    live["stream"] = "gold"; return live[["entry_time", "exit_time", "r", "stream"]]

def jpy_trades(own_filter):
    df, cost = load_sym("USDJPY"); pyramid.COST_OZ = cost
    t = pyramid.simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=trend_atr(df), add_at=(1.0,), flat_ny=16 + 50 / 60)
    if own_filter:
        ob = regime_flag(df, t); ei = df.set_index("time").index.get_indexer(pd.DatetimeIndex(t.entry_time))
        t = t[~ob[ei]]
    t["stream"] = "usdjpy"; return t[["entry_time", "exit_time", "r", "stream"]]

def one(args):
    name, hz, s = args
    t, ev, days = PREP[name]
    return name, hz, s, F.run_challenge(t, ev, days, s, F.scaled(1.25, 4, 0.25, int_total=5.0), horizon_days=hz,
                                        int_daily=2.5, int_total=5.0)[0]

PREP = {}
def init():
    g = gold_trades(); j0 = jpy_trades(False); j1 = jpy_trades(True)
    from multi import gold_bad_series
    gb = gold_bad_series()
    jb = j0[gb.reindex(pd.DatetimeIndex(j0.entry_time).floor("h")).fillna(False).values].copy()
    jh = jb.copy(); jh["w"] = 0.5; gw = g.copy(); gw["w"] = 1.0
    for name, t in (("gold", g), ("gold+jpy always", pd.concat([g, j0])), ("gold+jpy when gold BAD", pd.concat([g, jb])),
                    ("gold+jpy when BAD, half risk", pd.concat([gw, jh]))):
        PREP[name] = F.prepare(t)

if __name__ == "__main__":
    init()
    starts = [s for s in pd.date_range("2020-09-01", "2026-06-01", freq="3D", tz=F.PRAGUE) if s.weekday() < 5]
    jobs = [(n, hz, s) for n in PREP for hz in (30, 60, 90) for s in starts if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-25", tz="UTC")]
    with Pool(14, initializer=init) as p:
        res = p.map(one, jobs, chunksize=20)
    d = pd.DataFrame(res, columns=["name", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2019, 2021, 2023, 2024, 2026], labels=["2020-21", "2022-23", "2024", "2025-26"])
    d["pass"] = d.res == "pass"; d["stuck"] = d.res == "fail"
    tab = d.pivot_table(index=["name"], columns=["era", "hz"], values="pass", aggfunc="mean").round(2)
    pd.set_option("display.width", 300)
    print("PASS rate by start era / horizon days"); print(tab.to_string())
    print("\nSTUCK (can no longer trade under the 5% guard) rate");
    print(d.pivot_table(index="name", columns=["era"], values="stuck", aggfunc="mean").round(2).to_string())
