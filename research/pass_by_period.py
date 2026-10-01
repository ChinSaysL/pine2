"""Challenge pass rates, live risk settings, grouped by the year the challenge STARTS in (4 years FTMO data)."""
import warnings
import numpy as np
import pandas as pd
from ftmo_sim2 import prepare, run_challenge, scaled, fixed

warnings.filterwarnings("ignore")
t = pd.read_csv("ftmo_4y_raw_trades.csv", sep=";")
for c in ("entry", "exit"):
    t[f"{c}_time"] = (pd.to_datetime(t[f"{c}_time_ny"], format="%Y.%m.%d %H:%M")
                      .dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC"))
t = t.dropna(subset=["entry_time", "exit_time"])[["entry_time", "exit_time", "r"]]
tt, ev, days = prepare(t)
first = tt.entry_time.min().tz_convert("Europe/Prague").normalize()
last = tt.exit_time.max().tz_convert("Europe/Prague").normalize()
schemes = {"live: scaled 1.25%, guards 5%/2.5%": (scaled(1.25, 4, int_total=5.0), 5.0, 2.5),
           "previous: scaled 2%, guards 8%/4%": (scaled(2.0, 4, int_total=8.0), 8.0, 4.0),
           "fixed 1%, guards 5%/2.5%": (fixed(1.0), 5.0, 2.5)}
for name, (fn, it, idl) in schemes.items():
    print(f"\n{name}")
    for label, a, b in [("2022 Q4 - 2023", "2022-09-01", "2024-01-01"), ("2024", "2024-01-01", "2025-01-01"),
                        ("2025 - 2026", "2025-01-01", "2027-01-01"), ("all 4 years", "2022-09-01", "2027-01-01")]:
        row = []
        for hz in (30, 60, 90):
            starts = [first + pd.Timedelta(days=i) for i in range(0, (last - first).days - hz + 1)]
            starts = [s for s in starts if s.weekday() < 5 and pd.Timestamp(a, tz="Europe/Prague") <= s < pd.Timestamp(b, tz="Europe/Prague")]
            res = [run_challenge(tt, ev, days, s, fn, horizon_days=hz, int_total=it, int_daily=idl) for s in starts]
            row.append((np.mean([x[0] == "pass" for x in res]), np.mean([x[0] == "fail" for x in res]), len(starts)))
        print(f"  starts {label:14s} pass 1m {row[0][0]:4.0%}  2m {row[1][0]:4.0%}  3m {row[2][0]:4.0%}   "
              f"stuck at the loss guard within 3m {row[2][1]:4.0%}   ({row[2][2]} start days)")
