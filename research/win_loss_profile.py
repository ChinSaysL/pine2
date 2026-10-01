"""Do the wins make up for the losses? R-distribution of both engines.

Gold: the 2010-2026 real-EA export (research/mt5_bm_halfrisk.csv, live-equivalent settings).
Nasdaq: the local tester export (na.sdaq_tester_trades.csv in the terminal's Common folder).
"""
import os
import pandas as pd
import numpy as np

paths = [
    ("GOLD (2010-2026, live-equivalent)", r"c:\Users\Abdo\Downloads\pine2\research\mt5_bm_halfrisk.csv"),
    ("GOLD (last 12 months of it)", r"c:\Users\Abdo\Downloads\pine2\research\mt5_bm_halfrisk.csv"),
    ("NASDAQ (tester export)", os.path.join(os.environ["APPDATA"],
        r"MetaQuotes\Terminal\Common\Files\GoldBreakout\nasdaq_tester_trades.csv")),
]

for label, path in paths:
    if not os.path.exists(path):
        print(f"{label}: file not found ({path})")
        continue
    t = pd.read_csv(path, sep=";")
    if "r" not in t:
        print(f"{label}: no r column"); continue
    if "entry_time_ny" in t:
        t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
        t = t.dropna(subset=["et"]).sort_values("et")
        if "last 12" in label:
            t = t[t.et >= t.et.max() - pd.Timedelta(days=365)]
    r = t.r.values
    w, l = r[r > 0], r[r < 0]
    print("=" * 78)
    print(f"{label}: {len(r)} trades")
    print(f"  win rate            {100*len(w)/len(r):.0f}%   ({len(w)} wins / {len(l)} losses)")
    print(f"  average win         {w.mean():+.2f}R")
    print(f"  average loss        {l.mean():+.2f}R")
    print(f"  best / worst        {r.max():+.1f}R / {r.min():+.1f}R")
    print(f"  expectancy          {r.mean():+.3f}R per trade  ->  {r.sum():+.0f}R total")
    print(f"  payoff (avgW/|avgL|) {w.mean()/abs(l.mean()):.2f}   needs a win rate of "
          f"{100*abs(l.mean())/(w.mean()+abs(l.mean())):.0f}% to break even")
    q = np.percentile(r, [10, 25, 50, 75, 90])
    print(f"  R percentiles       10% {q[0]:+.2f}  25% {q[1]:+.2f}  50% {q[2]:+.2f}  75% {q[3]:+.2f}  90% {q[4]:+.2f}")
    for th in (1, 2, 3, 5):
        print(f"  trades >= +{th}R       {100*(r >= th).mean():4.0f}%   (they carry {w[w>=th].sum():+.0f}R of {w.sum():+.0f}R of all wins)")
    print(f"  trades at about -1R  {100*((r <= -0.8) & (r >= -1.2)).mean():.0f}%   (typical loss {np.median(l):+.2f}R)")
