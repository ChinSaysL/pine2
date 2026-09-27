import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
from regime import load_mt5, paper_trades, regime_flag
from range_concepts import run, c1_failed_breakout, c2_stretch_fade, summary
df = load_mt5("H1")
bad = regime_flag(df, paper_trades(df))
rows = []
for label, fn in [("C1 fail-BO mid", c1_failed_breakout(df)), ("C2 stretch 2ATR", c2_stretch_fade(df))]:
    for mode, allowed in [("all hours", None), ("BAD only", bad), ("GOOD only", ~bad)]:
        t = run(df, fn, allowed=allowed)
        rows.append(summary(t, f"{label} | {mode}"))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).to_string(index=False))
