"""Do gold breakouts entered in the thin Asian hours (19:00-01:00 New York) pay off?
Uses the existing 2010-2026 real-EA exports in research/mt5_bm_*.csv (from run_badmode.ps1)."""
import glob
import pandas as pd
import numpy as np

for path in sorted(glob.glob(r"c:\Users\Abdo\Downloads\pine2\research\mt5_bm_*.csv")) + \
            sorted(glob.glob(r"c:\Users\Abdo\Downloads\pine2\research\mt5_fixed1.csv")):
    t = pd.read_csv(path, sep=";")
    if "entry_time_ny" not in t or "r" not in t:
        continue
    et = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
    t = t.assign(et=et).dropna(subset=["et"])
    if not len(t):
        continue
    t["ny_min"] = t.et.dt.hour * 60 + t.et.dt.minute
    t["year"] = t.et.dt.year
    hourly = t.groupby(t.ny_min // 60).r.agg(["count", "sum", "mean"]).round(2)
    asian = t[(t.ny_min >= 19 * 60) | (t.ny_min < 60)]
    other = t[(t.ny_min >= 60) & (t.ny_min < 19 * 60)]
    print("=" * 90)
    print(f"{path.split(chr(92))[-1]}   {len(t)} trades  {t.et.min():%Y-%m-%d} .. {t.et.max():%Y-%m-%d}")
    print(f"  Asian window 19:00-01:00 NY : {len(asian):4d} trades  {asian.r.sum():+7.1f}R  PF {asian.r[asian.r>0].sum()/max(-asian.r[asian.r<0].sum(),1e-9):.2f}  win {(asian.r>0).mean():.0%}")
    print(f"  rest of the day             : {len(other):4d} trades  {other.r.sum():+7.1f}R  PF {other.r[other.r>0].sum()/max(-other.r[other.r<0].sum(),1e-9):.2f}  win {(other.r>0).mean():.0%}")
    print(f"  total                       : {len(t):4d} trades  {t.r.sum():+7.1f}R")
    print("  R by entry hour (NY):")
    print(hourly.T.to_string())
    ya = asian.groupby("year").r.sum().round(1)
    yo = other.groupby("year").r.sum().round(1)
    print("  Asian R by year: ", ya.to_dict())
    print("  Other R by year: ", yo.to_dict())
