import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
from regime import load_mt5, paper_trades, regime_flag
from range_concepts import summary
from orb import orb
h1 = load_mt5("H1")
bad_h1 = pd.Series(regime_flag(h1, paper_trades(h1)), index=h1.time)
m15 = load_mt5("M15")
bad = bad_h1.reindex(m15.time.dt.floor("h")).fillna(False).values
print("M15 from", m15.time.iloc[0])
rows = []
for rng in (0.5, 1.0, 1.5, 2.0):
    for slip in (0.02, 0.1):
        for mode, allowed in (("BAD", bad), ("GOOD", ~bad)):
            t = orb(m15, allowed, range_h=rng, tgt_r=2.0, slip_atr=slip)
            s = summary(t, f"M15 {mode} rng{rng}h tgt2 slip{slip}")
            rows.append(s)
t1 = orb(h1, bad_h1.values, range_h=1.0, tgt_r=2.0, slip_atr=0.05)
rows.append(summary(t1, "H1 BAD rng1h (reference)"))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).drop(columns=["dev 20-01..22-06"]).to_string(index=False))
t = orb(m15, bad, range_h=1.0, tgt_r=2.0, slip_atr=0.1); t["q"] = t.entry_time.dt.to_period("Q")
print(t.groupby("q").r.agg(["count", "sum"]).round(1).T.to_string())
