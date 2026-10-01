import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
from regime import load_mt5, paper_trades, regime_flag
from range_concepts import summary
from orb import orb
df = load_mt5("H1")
bad = regime_flag(df, paper_trades(df))
rows = []
for rng in (1.0, 2.0, 3.0):
    for tgt in (1.5, 2.0, 3.0, None):
        t = orb(df, bad, range_h=rng, tgt_r=tgt, slip_atr=0.05)
        rows.append(summary(t, f"BAD rng{rng:.0f}h tgt{tgt} slip.05"))
for st in (7.0, 9.0):
    rows.append(summary(orb(df, bad, start=st, slip_atr=0.05), f"BAD start{st:.0f}NY rng2 tgt2"))
rows.append(summary(orb(df, bad, start=3.0, slip_atr=0.05), "BAD LONDON 03NY rng2 tgt2"))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).to_string(index=False))
t = orb(df, bad, slip_atr=0.05); t["y"] = t.entry_time.dt.year
print(t.groupby("y").r.agg(["count", "sum", "mean"]).round(2))
