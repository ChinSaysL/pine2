"""MT5 Strategy Tester (MetaQuotes data) vs TradingView (OANDA data): same trades?"""
import sys
import numpy as np
import pandas as pd

name = sys.argv[1] if len(sys.argv) > 1 else "fixed1"
mt = pd.read_csv(f"mt5_{name}.csv", sep=";")
tv = pd.read_csv("gpyr.csv", sep=";")
mt["et"] = pd.to_datetime(mt.entry_time_ny, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
tv["et"] = pd.to_datetime(tv.entry_time).dt.tz_localize("UTC").dt.tz_convert("America/New_York")
mt = mt.dropna(subset=["et"])
start = pd.Timestamp("2025-01-15", tz="America/New_York")
mt, tv = mt[mt.et >= start], tv[tv.et >= start]


def sc(r):
    r = np.asarray(r, float)
    cum = np.concatenate([[0], np.cumsum(r)])
    return f"{len(r)} units {r.sum():+.1f}R PF {r[r > 0].sum() / -r[r < 0].sum():.2f} maxDD {np.max(np.maximum.accumulate(cum) - cum):.1f}R win {(r > 0).mean():.0%}"


print("MT5 :", sc(mt.r))
print("TV  :", sc(tv.r))
# match: same direction, entry within the same hour (MT5 fills intrabar, TV reports the bar)
mt["hour"] = mt.et.dt.floor("h")
tv["hour"] = tv.et.dt.floor("h")
m = mt.merge(tv, on=["hour"], suffixes=("_mt", "_tv"))
m = m[m.dir_mt == m.dir_tv]
print(f"matched entries (same hour & side): {len(m)} of MT5 {len(mt)} / TV {len(tv)}")
print(f"entry price difference MT5-TV: median {np.median(m.entry_mt - m.entry_tv):+.2f}, mean |diff| {np.mean(np.abs(m.entry_mt - m.entry_tv)):.2f}")
print(f"R of matched trades: MT5 {m.r_mt.sum():+.1f}  TV {m.r_tv.sum():+.1f}")
for y, g in mt.groupby(mt.et.dt.year):
    print(" MT5", y, sc(g.r))
for y, g in tv.groupby(tv.et.dt.year):
    print(" TV ", y, sc(g.r))
print("MT5 exit reasons:", mt.comment.value_counts().to_dict())
print("MT5 risk per trade $: median", mt.risk_usd.median(), " min", mt.risk_usd.min(), " max", mt.risk_usd.max())
