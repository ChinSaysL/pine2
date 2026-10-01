"""Drawdown and losing-streak profile of the loss-limiting candidates (H1 simulator)."""
import numpy as np
import pandas as pd
import h1sim
import gold_variants as gv

t, h = h1sim.load()
base = gv.base.sort_values("et").reset_index(drop=True)

GRID = [
    ("live now",                               dict()),
    ("no BE after add",                        dict(be_after_add=False)),
    ("stop 1.25 + no BE",                      dict(stop_atr=1.25, be_after_add=False)),
    ("stop 1.25 + no BE + re-entry",           dict(stop_atr=1.25, be_after_add=False, reverse=True,
                                                    rev_same_dir=True, rev_stop_atr=1.0, rev_max_bars=48)),
    ("stop 1.0 + no BE + re-entry",            dict(stop_atr=1.0, be_after_add=False, reverse=True,
                                                    rev_same_dir=True, rev_stop_atr=1.5, rev_max_bars=48)),
]

rows = []
for label, kw in GRID:
    df = h1sim.simulate(base, h, **kw)
    df = df.sort_values("et")
    r = (df.r + df.rev.fillna(0)).values
    cum = np.concatenate([[0], np.cumsum(r)])
    dd = np.max(np.maximum.accumulate(cum) - cum)
    # longest run of consecutive losing trades
    streak = best = 0
    for x in r:
        streak = streak + 1 if x < 0 else 0
        best = max(best, streak)
    worst20 = min(np.convolve(r, np.ones(20), "valid")) if len(r) > 20 else np.nan
    worst50 = min(np.convolve(r, np.ones(50), "valid")) if len(r) > 50 else np.nan
    rows.append(dict(setup=label, trades=len(r), total=round(r.sum(), 1), per_year=round(r.sum() / 7, 1),
                     maxDD=round(dd, 1), worst20=round(worst20, 1), worst50=round(worst50, 1),
                     loss_streak=best, win=round(100 * (r > 0).mean())))
print(pd.DataFrame(rows).to_string(index=False))
print("\n(a trade here = one entry; re-entry legs are extra trades in the same R units, both risking 1 unit)")
