"""Compare the minimum-close-penetration tester variants.

Each file is the gold EA's tester export (tester_trades.csv): one row per closed position with
NY times, direction, entry/exit, lots, profit, risk in USD and R.
"""
import glob
import os
import pandas as pd
import numpy as np

R = r"c:\Users\Abdo\Downloads\pine2\research"
ORDER = ["cc_off", "cc_p000", "cc_p010", "cc_p015", "cc_p025", "cc_p040", "cc_p060"]
LABEL = {"cc_off": "off (live)", "cc_p000": "close > level", "cc_p010": "close >= +0.10 ATR",
         "cc_p015": "close >= +0.15 ATR", "cc_p025": "close >= +0.25 ATR",
         "cc_p040": "close >= +0.40 ATR", "cc_p060": "close >= +0.60 ATR"}


def load(name):
    p = os.path.join(R, f"mt5_{name}.csv")
    if not os.path.exists(p):
        return None
    t = pd.read_csv(p, sep=";")
    t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
    t["key"] = t.et.astype(str) + "|" + t.dir.astype(str)
    return t


def pf(r):
    return r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)


data = {n: load(n) for n in ORDER}
base = data["cc_off"]
if base is None:
    raise SystemExit("no control export yet")

print(f"{'variant':22} {'trades':>6} {'total R':>9} {'PF':>5} {'win%':>5} {'avgR':>6}  {'maxDD':>6}")
for n in ORDER:
    t = data[n]
    if t is None:
        print(f"{LABEL[n]:22} {'(missing)':>6}")
        continue
    r = t.r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    dd = np.max(np.maximum.accumulate(cum) - cum)
    print(f"{LABEL[n]:22} {len(r):6d} {r.sum():+9.1f} {pf(r):5.2f} {100*(r>0).mean():5.0f} {r.mean():6.3f}  {dd:6.1f}")

print("\nby year (total R)")
years = sorted(base.et.dt.year.dropna().unique())
print(f"{'year':6}" + "".join(f"{LABEL[n][:14]:>16}" for n in ORDER))
for y in years:
    row = f"{int(y):6}"
    for n in ORDER:
        t = data[n]
        row += f"{(t[t.et.dt.year == y].r.sum() if t is not None else float('nan')):16.1f}"
    print(row)

print("\ntrades the gate removed (control trades absent from the variant) and their R")
for n in ORDER[1:]:
    t = data[n]
    if t is None:
        continue
    gone = base[~base.key.isin(set(t.key))]
    print(f"  {LABEL[n]:22} removed {len(gone):4d} trades {gone.r.sum():+8.1f}R   "
          f"(winners {len(gone[gone.r>0]):3d} {gone.r[gone.r>0].sum():+6.1f}R, losers {len(gone[gone.r<0]):3d} {gone.r[gone.r<0].sum():+6.1f}R)")

# the 2026-09-30 20:16 New York sweep trade
print("\nthe sweep trade (entry 2026-09-30 20:16 NY, SELL):")
for n in ORDER:
    t = data[n]
    if t is None:
        continue
    m = t[t.entry_time_ny.astype(str).str.startswith("2026.09.30 20:1")]
    print(f"  {LABEL[n]:22} " + ("taken: " + m.to_string(index=False).replace("\n", " | ") if len(m) else "not taken"))
