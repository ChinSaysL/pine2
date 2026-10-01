"""Fade concepts on the multi-asset universe (pre-registered, same params as the gold tests) +
USDJPY breakout robustness.  Judged on trades while GOLD is BAD, by period; and per-year."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import range_concepts as rc, pyramid
from multi import load_sym, trend_atr, gold_bad_series, PERIODS, DATA
from regime import regime_flag

def fade_work(sym):
    df, cost = load_sym(sym)
    rc.COST_OZ = cost
    gb = gold_bad_series()
    out = []
    for name, fn in (("F1 failBO", rc.c1_failed_breakout(df)), ("F2 stretch", rc.c2_stretch_fade(df))):
        t = rc.run(df, fn)
        if not len(t): continue
        t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values
        ob = regime_flag(df, t)
        t["obad"] = ob[df.set_index("time").index.get_indexer(pd.DatetimeIndex(t.entry_time))]
        t["sym"], t["strat"] = sym, name
        out.append(t)
    return out

def jpy_work(args):
    hours, band, trail = args
    df, cost = load_sym("USDJPY"); pyramid.COST_OZ = cost
    t = pyramid.simulate_pyr(df, hours=hours, stop_atr=2.0, trail_atr=trail, trend=trend_atr(df, band_atr=band), add_at=(1.0,), flat_ny=16 + 50 / 60)
    t["y"] = pd.to_datetime(t.entry_time).dt.year
    return args, t.groupby("y").r.sum().round(1).to_dict(), round(t.r.sum(), 1), len(t)

if __name__ == "__main__":
    syms = [s for s in pd.read_csv(f"{DATA}\XX_meta.csv").sym if s != "XAGUSD"]
    with Pool(14) as p:
        res = [t for r in p.imap_unordered(fade_work, syms) for t in r]
        jr = p.map(jpy_work, [(h, b, tr) for h in (12, 24, 48) for b in (0.5, 0.75, 1.0) for tr in (3.0,)] + [(24, 0.75, 2.0), (24, 0.75, 4.0)])
    t = pd.concat(res); t.to_pickle("multi_fade.pkl")
    for strat, g in t.groupby("strat"):
        print("==", strat)
        for lab, m in (("gold BAD all mkts", g.gbad), ("gold BAD own GOOD", g.gbad & ~g.obad)):
            print(lab.ljust(20), " | ".join(f"{p}: {g[m & (g.entry_time >= a) & (g.entry_time < b)].r.sum():+7.1f}R" for p, a, b in PERIODS))
        rows = []
        for sym, s in g[g.gbad].groupby("sym"):
            rows.append([sym] + [round(s[(s.entry_time >= a) & (s.entry_time < b)].r.sum(), 1) for p, a, b in PERIODS])
        d = pd.DataFrame(rows, columns=["sym", "dev", "holdA", "holdB"])
        print("positive in all 3 periods:", d[(d.dev > 0) & (d.holdA > 0) & (d.holdB > 0)].to_string(index=False))
    print("== USDJPY breakout neighbours (hours, band_atr, trail) -> R by year, total, n")
    for a, y, tot, n in jr: print(a, y, tot, n)
