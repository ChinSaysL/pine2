"""Aggregate the one-year-window A/B of the minimum-close-penetration rule.

Files: cc_y<year>_<variant>.csv (gold EA tester export, NY times).
Variants: off (live behaviour), p000 (close must be beyond the level), p015 / p025 / p040.
"""
import glob
import os
import re
import pandas as pd
import numpy as np

R = r"c:\Users\Abdo\Downloads\pine2\research"
PENS = ["off", "p000", "p015", "p025", "p040"]
LABEL = {"off": "off (live)", "p000": "close beyond level", "p015": "close >= +0.15 ATR",
         "p025": "close >= +0.25 ATR", "p040": "close >= +0.40 ATR"}


def load(path):
    t = pd.read_csv(path, sep=";")
    t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
    t["key"] = t.et.astype(str) + "|" + t.dir.astype(str)
    t["year"] = t.entry_time_ny.str.slice(0, 4)
    return t.dropna(subset=["et"])


data = {}
for p in PENS:
    frames = [load(f) for f in sorted(glob.glob(os.path.join(R, f"cc_y*_{p}.csv")))]
    frames = [f for f in frames if len(f)]
    if frames:
        data[p] = pd.concat(frames, ignore_index=True)
if "off" not in data:
    raise SystemExit("no control data yet")


def pf(r):
    return r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)


print("=== pooled over all available one-year windows (fixed 1% risk, limits 50/50)")
print(f"{'variant':20} {'trades':>7} {'total R':>9} {'PF':>5} {'win%':>6} {'avgR':>7} {'years':>6}")
base = data["off"]
for p in PENS:
    if p not in data:
        continue
    t = data[p]
    print(f"{LABEL[p]:20} {len(t):7d} {t.r.sum():+9.1f} {pf(t.r):5.2f} {100*(t.r>0).mean():6.0f} {t.r.mean():7.3f} {t.year.nunique():6d}")

print("\n=== per year (total R, trades in brackets)")
years = sorted(base.year.unique())
print(f"{'year':6}" + "".join(f"{LABEL[p][:16]:>20}" for p in PENS if p in data))
for y in years:
    row = f"{y:6}"
    for p in PENS:
        if p not in data:
            continue
        s = data[p][data[p].year == y]
        row += f"{s.r.sum():>13.1f} ({len(s):>3})"
    print(row)

print("\n=== trades the gate removed (control trades missing from the variant)")
for p in PENS:
    if p == "off" or p not in data:
        continue
    gone = base[~base.key.isin(set(data[p].key))]
    print(f"  {LABEL[p]:20} removed {len(gone):4d} of {len(base)} trades, {gone.r.sum():+8.1f}R "
          f"(winners {len(gone[gone.r > 0]):3d} {gone.r[gone.r > 0].sum():+7.1f}R, losers {len(gone[gone.r < 0]):3d} {gone.r[gone.r < 0].sum():+7.1f}R)")

print("\n=== the 2026-09-30 20:16 New York sweep trade (today's loss) in each variant")
for p in PENS:
    if p not in data:
        continue
    m = data[p][data[p].entry_time_ny.astype(str).str.startswith("2026.09.30 20:")]
    print(f"  {LABEL[p]:20} " + (f"taken  {m.iloc[0].dir} entry {m.iloc[0].entry:.2f} r={m.iloc[0].r:+.2f}" if len(m) else "NOT taken"))
