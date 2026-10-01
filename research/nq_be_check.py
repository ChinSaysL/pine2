"""Robustness check for the winning rule (afternoon break-even):
how many ORB trades does it change, and is the gain broad or a few lucky trades?
Writes nq_be_check.txt."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import nq_exits as X

days, D, cost = X.load_days()
rows = []
for day, x in days.items():
    s = X.orb_setup(x, D, day)
    if not s:
        continue
    dr, e, st, k0 = s
    a = X.walk(x, k0, dr, e, st, cost, {})
    b = X.walk(x, k0, dr, e, st, cost, dict(be_at=780, be_at_min=0.5))
    if a and b:
        rows.append(dict(day=day, live=a[0], be=b[0], hm=a[1], hm_be=b[1],
                         peak=X.peak_r(x, k0, dr, e, st)))
t = pd.DataFrame(rows)
t["year"] = pd.to_datetime(t.day).dt.year
t["d"] = t.be - t.live
ch = t[t.d.abs() > 1e-9]
lines = []
lines.append(f"ORB trades: {len(t)}   changed by the rule: {len(ch)} ({100*len(ch)/len(t):.1f}%)")
lines.append(f"total R live {t.live.sum():+.1f}  ->  with afternoon BE {t.be.sum():+.1f}   (delta {t.d.sum():+.1f}R)")
lines.append(f"per changed trade: mean {ch.d.mean():+.3f}R  median {ch.d.median():+.3f}R  best {ch.d.max():+.2f}R  worst {ch.d.min():+.2f}R")
lines.append(f"changed trades improved {int((ch.d > 0).sum())} / hurt {int((ch.d < 0).sum())}")
lines.append(f"delta by year: " + t.groupby('year').d.sum().round(2).to_string().replace('\n', ' | '))
lines.append("")
lines.append("years where the rule changed a trade:")
lines.append(t[t.d.abs() > 1e-9].groupby("year").d.agg(["count", "sum"]).round(2).to_string())
lines.append("")
lines.append("the 8 biggest improvements:")
lines.append(ch.sort_values("d", ascending=False).head(8)[["day", "live", "be", "d", "peak"]].round(2).to_string(index=False))
lines.append("")
lines.append("the 5 biggest give-ups:")
lines.append(ch.sort_values("d").head(5)[["day", "live", "be", "d", "peak"]].round(2).to_string(index=False))
txt = "\n".join(lines)
with open("nq_be_check.txt", "w", encoding="utf-8") as f:
    f.write(txt)
print(txt)
