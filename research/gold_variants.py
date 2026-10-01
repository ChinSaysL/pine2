"""Structural variants on the real gold entries, via the H1 simulator (unit-based)."""
import numpy as np
import pandas as pd
import h1sim

t, h = h1sim.load()
print(f"real entries in the H1 window: {len(t)}  ({t.et.min():%Y-%m-%d} .. {t.et.max():%Y-%m-%d})")
t["exit_key"] = t.exit_time_ny + "|" + t.dir
t["is_add"] = False
for key, idx in t.groupby("exit_key").groups.items():
    if len(idx) > 1:
        sub = t.loc[idx].sort_values("entry_time_ny")
        t.loc[sub.index[1:], "is_add"] = True
print(f"base entries {int((~t.is_add).sum())}, add rows {int(t.is_add.sum())}")
base = t[~t.is_add].reset_index(drop=True)


def run(label, sample, **kw):
    df = h1sim.simulate(sample, h, **kw)
    return h1sim.stats(df, label), df


print("\n=== validation (one row per input row, unit-based)")
for name, sample in (("all rows", t), ("base rows only", base)):
    s, _ = run(name, sample)
    print(f"  {name:16} n {s['n']:5d}  total {s['total']:+8.1f}R  avg {s['avg']:+.3f}  win {s['win']}%  PF {s['pf']}")
print(f"  export reference   n {len(t):5d}  total {t.r.sum():+8.1f}R  avg {t.r.mean():+.3f}  win {round(100*(t.r>0).mean())}%")

VARIANTS = [
    ("baseline",                                {}),
    ("no BE after the add",                     dict(be_after_add=False)),
    ("no add at all",                           dict(add_levels=())),
    ("add at +1.5R, no BE",                     dict(add_levels=(1.5,), be_after_add=False)),
    ("adds +1R +2R, no BE",                     dict(add_levels=(1.0, 2.0), be_after_add=False)),
    ("trail 4 (no BE)",                         dict(trail_atr=4.0, be_after_add=False)),
    ("trail 5 (no BE)",                         dict(trail_atr=5.0, be_after_add=False)),
    ("stop 1.0 ATR",                            dict(stop_atr=1.0)),
    ("stop 1.0 ATR + no BE",                    dict(stop_atr=1.0, be_after_add=False)),
    ("stop 1.25 ATR + no BE",                   dict(stop_atr=1.25, be_after_add=False)),
    ("stop 1.5 ATR + no BE",                    dict(stop_atr=1.5, be_after_add=False)),
    ("stop 1.0 + no BE + trail 5",              dict(stop_atr=1.0, be_after_add=False, trail_atr=5.0)),
    ("stop 1.25 + no BE + trail 5",             dict(stop_atr=1.25, be_after_add=False, trail_atr=5.0)),
    ("stop 1.0 + no BE + trail 5 + add 1.5",    dict(stop_atr=1.0, be_after_add=False, trail_atr=5.0, add_levels=(1.5,))),
    ("stop 2 + no BE + trail 5",                dict(stop_atr=2.0, be_after_add=False, trail_atr=5.0)),
    ("time stop <+0.3R after 6 bars",           dict(time_stop_bars=6, time_stop_min_r=0.3)),
    ("time stop <+0.3R after 12 bars",          dict(time_stop_bars=12, time_stop_min_r=0.3)),
]

print("\n=== structural variants (792 base entries, identical sample for every variant)")
rows, saved = [], {}
for label, kw in VARIANTS:
    s, df = run(label, base, **kw)
    rows.append(s)
    saved[label] = df
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== by year (total R)")
years = sorted(base.et.dt.year.unique())
key_variants = ["baseline", "no BE after the add", "stop 1.0 ATR + no BE", "stop 1.25 + no BE + trail 5"]
out = pd.DataFrame(index=years)
for k in key_variants:
    df = saved[k]
    out[k] = [round(df[df.year == y].r.sum(), 1) for y in years]
print(out.to_string())

print("\n=== after a stop: fade (reverse) vs continuation (re-enter the same way)")
rows = []
for label, same in (("fade", False), ("continuation re-entry", True)):
    for revstop in (1.0, 2.0):
        for revmax in (12, 48):
            s, df = run("x", base, reverse=True, rev_same_dir=same, rev_stop_atr=revstop,
                        rev_max_bars=revmax, rev_trail_atr=3.0)
            rv = df.rev.dropna()
            rows.append(dict(setup=f"{label} stop {revstop} ATR / {revmax} bars", extra_trades=int(len(rv)),
                             first_total=round(df.r.sum(), 1), second_total=round(rv.sum(), 1),
                             second_avg=round(rv.mean(), 3), second_win=round(100 * (rv > 0).mean()),
                             combined=round((df.r + df.rev.fillna(0)).sum(), 1)))
print(pd.DataFrame(rows).to_string(index=False))
saved["stop 1.0 ATR + no BE"].to_csv(h1sim.R_DIR + r"\variant_stop1_nobe.csv", index=False)
