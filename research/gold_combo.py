"""Combination + stability test: tight stop, no BE after the add, continuation re-entry after a stop."""
import numpy as np
import pandas as pd
import h1sim
import gold_variants as gv

t, h = h1sim.load()
base = gv.base

GRID = [
    ("live now",                                   dict()),
    ("no BE after add",                            dict(be_after_add=False)),
    ("stop 1.25 + no BE",                          dict(stop_atr=1.25, be_after_add=False)),
    ("stop 1.25 + no BE + re-entry 1.0ATR/48",     dict(stop_atr=1.25, be_after_add=False, reverse=True,
                                                        rev_same_dir=True, rev_stop_atr=1.0, rev_max_bars=48)),
    ("stop 2 + no BE + re-entry 1.0ATR/48",        dict(be_after_add=False, reverse=True,
                                                        rev_same_dir=True, rev_stop_atr=1.0, rev_max_bars=48)),
    ("stop 1.0 + no BE + re-entry 1.5ATR/48",      dict(stop_atr=1.0, be_after_add=False, reverse=True,
                                                        rev_same_dir=True, rev_stop_atr=1.5, rev_max_bars=48)),
    ("stop 2 + no BE + fade 2.0ATR/48",            dict(be_after_add=False, reverse=True, rev_same_dir=False,
                                                        rev_stop_atr=2.0, rev_max_bars=48)),
]

print("=== combinations (base entries, same sample; 'total' includes the re-entry legs)")
rows, per_year = [], {}
for label, kw in GRID:
    df = h1sim.simulate(base, h, **kw)
    r = df.r + df.rev.fillna(0)
    rows.append(dict(label=label, first_legs=len(df), re_entries=int(df.rev.notna().sum()),
                     total=round(r.sum(), 1), pf=round(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), 2),
                     win=round(100 * (r > 0).mean()), avg=round(r.mean(), 3)))
    per_year[label] = [round(r[df.year == y].sum(), 1) for y in sorted(base.et.dt.year.unique())]
print(pd.DataFrame(rows).to_string(index=False))
print("\n=== by year")
years = sorted(base.et.dt.year.unique())
print(pd.DataFrame(per_year, index=years).to_string())

print("\n=== how often does the re-entry exist / what does it add")
df = h1sim.simulate(base, h, be_after_add=False, reverse=True, rev_same_dir=True,
                    rev_stop_atr=1.0, rev_max_bars=48)
re = df.rev.dropna()
print(f"  stop-outs {len(re)} of {len(df)} entries ({100*len(re)/len(df):.0f}%)")
print(f"  re-entry R: mean {re.mean():+.3f}  median {re.median():+.3f}  win {100*(re>0).mean():.0f}%  "
      f"sum {re.sum():+.1f}R   best {re.max():+.2f}R  worst {re.min():+.2f}R")
print("  re-entry R by year:", {int(y): round(v, 1) for y, v in re.groupby(df.year[df.rev.notna()]).sum().items()})
