"""Where does the H1 simulator diverge from the real EA? Compare per-trade R and exit reasons."""
import numpy as np
import pandas as pd
import h1sim
import gold_variants as gv   # reuses the loaded sample (runs the whole driver once)

t, h = h1sim.load()
sim = h1sim.simulate(gv.base, h)
sim["et_key"] = pd.to_datetime(sim.et).dt.tz_convert("UTC")
b = gv.base.copy()
b["et_key"] = b.et_utc
m = b.merge(sim, on="et_key", suffixes=("_real", "_sim"))
m["diff"] = m.r_sim - m.r_real
print(f"matched {len(m)} base entries   real {m.r_real.sum():+.1f}R   sim {m.r_sim.sum():+.1f}R   "
      f"diff {m['diff'].sum():+.1f}R")
print(f"  mean |diff| {m['diff'].abs().mean():.3f}R   median diff {m['diff'].median():+.3f}R")
print("\nby real exit reason:")
print(m.groupby("comment").agg(n=("diff", "size"), real=("r_real", "sum"), sim=("r_sim", "sum"),
                               diff=("diff", "sum")).round(1).to_string())
print("\nby sim exit reason:")
print(m.groupby("why").agg(n=("diff", "size"), real=("r_real", "sum"), sim=("r_sim", "sum"),
                           diff=("diff", "sum")).round(1).to_string())
print("\nreal exit reason shares: ", (m.comment.value_counts(normalize=True) * 100).round(0).to_dict())
print("sim  exit reason shares: ", (m.why.value_counts(normalize=True) * 100).round(0).to_dict())
print("\nlargest divergences (real vs sim):")
m["dir"] = m.dir_real.map({1: "L", -1: "S"})
cols = ["entry_time_ny", "exit_time_ny", "dir", "r_real", "r_sim", "diff", "comment", "why", "units"]
print(m.reindex(m["diff"].abs().sort_values(ascending=False).index)[cols].head(12).to_string(index=False))
print("\nsim trades carrying an add (units>1):", int((sim.units > 1).sum()), "of", len(sim))
print("\ndistribution of diff (sim - real):")
print(m["diff"].describe(percentiles=[.05, .25, .5, .75, .95]).round(3).to_string())
