"""Loss anatomy of the gold engine: where do the losses come from, and are they attackable?

Uses the 2010-2026 real-EA export (research/mt5_bm_halfrisk.csv) plus the local H1 bars
(research/data/XAUUSD_H1.csv) for what happened after each loss.
"""
import pandas as pd
import numpy as np

R = r"c:\Users\Abdo\Downloads\pine2\research"
t = pd.read_csv(R + r"\mt5_bm_halfrisk.csv", sep=";")
t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
t["xt"] = pd.to_datetime(t.exit_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
t = t.dropna(subset=["et", "xt"])
t["et_utc"] = t.et.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
t["xt_utc"] = t.xt.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
t = t.dropna(subset=["et_utc", "xt_utc"])
t["ny_hour"] = t.et.dt.hour
t["year"] = t.et.dt.year
n = len(t)
print(f"trades: {n}  {t.et_utc.min():%Y-%m-%d} .. {t.et_utc.max():%Y-%m-%d}  total {t.r.sum():+.1f}R")
print(f"wins {(t.r>0).sum()}  losses {(t.r<0).sum()}  flat {(t.r==0).sum()}")

print("\n=== loss anatomy by size")
bins = [(-100, -0.95, "full stop  -1R"), (-0.95, -0.6, "-1R to -0.6R"), (-0.6, -0.3, "-0.6 to -0.3R"),
        (-0.3, 0, "-0.3R to 0"), (0, 0.3, "0 to +0.3R")]
for lo, hi, name in bins:
    s = t[(t.r > lo) & (t.r <= hi)]
    print(f"  {name:16} n {len(s):5d} ({100*len(s)/n:4.1f}%)  sum {s.r.sum():+8.1f}R   avg {s.r.mean():+.2f}R")
print(f"  wins > +3R       n {len(t[t.r>3]):5d} ({100*len(t[t.r>3])/n:4.1f}%)  sum {t.r[t.r>3].sum():+8.1f}R")

print("\n=== by exit reason (EA's own comment, R-based)")
g = t.groupby("comment").agg(n=("r", "size"), total=("r", "sum"), avg=("r", "mean")).sort_values("total")
print(g.round(2).to_string())

print("\n=== time in trade (H1 bars, approx from NY minutes)")
t["mins"] = (t.xt - t.et).dt.total_seconds() / 60
for lo, hi, name in [(-1, 60, "<1h"), (60, 240, "1-4h"), (240, 720, "4-12h"), (720, 1440, "12-24h"), (1440, 1e9, ">24h")]:
    s = t[(t.mins > lo) & (t.mins <= hi)]
    print(f"  {name:8} n {len(s):5d}  sum {s.r.sum():+8.1f}R  avg {s.r.mean():+.2f}R  win {100*(s.r>0).mean():4.0f}%")

print("\n=== by entry hour (New York)")
g = t.groupby("ny_hour").agg(n=("r", "size"), total=("r", "sum"), avg=("r", "mean"),
                             winrate=("r", lambda x: 100 * (x > 0).mean())).round(2)
print(g.to_string())

# ---- what happened AFTER each full-stop loss ------------------------------------------------
H = pd.read_csv(R + r"\data\XAUUSD_H1.csv", parse_dates=["utc"]).sort_values("utc").reset_index(drop=True)
utc = H.utc.values
hi, lo, cl = H.high.values, H.low.values, H.close.values
print("\n=== after each full-stop loss (-1R): could a reverse trade have paid?")
print("    (reverse = enter opposite at the stop price; MFE/MAE in units of the original risk R)")
rows = []
full = t[(t.r <= -0.95)].copy()
for tr in full.itertuples():
    a = np.searchsorted(utc, np.datetime64(tr.xt_utc.replace(tzinfo=None)))
    if a >= len(H) - 1:
        continue
    risk = abs(tr.entry - tr.exit) if tr.exit != tr.entry else np.nan
    if not np.isfinite(risk) or risk <= 0:
        risk = abs(tr.risk_usd / (tr.lots * 100))
    best = {}
    for bars in (4, 8, 24, 48):
        b = min(a + bars, len(H) - 1)
        if tr.dir == "S":   # we were short -> reverse is long
            mfe = (hi[a + 1:b + 1].max() - tr.exit) / risk if b > a else 0
            mae = (tr.exit - lo[a + 1:b + 1].min()) / risk if b > a else 0
        else:
            mfe = (tr.exit - lo[a + 1:b + 1].min()) / risk if b > a else 0
            mae = (hi[a + 1:b + 1].max() - tr.exit) / risk if b > a else 0
        best[f"mfe{bars}"] = mfe
        best[f"mae{bars}"] = mae
    # did price come back through the original level (the broken extreme) within 24 bars?
    lvl = tr.entry
    back = (lo[a + 1:a + 25].min() <= lvl) if tr.dir == "S" else (hi[a + 1:a + 25].max() >= lvl)
    rows.append(dict(r=tr.r, dir=tr.dir, **best, back_through_level=back))
f = pd.DataFrame(rows)
print(f"  sample: {len(f)} full-stop losses")
for bars in (4, 8, 24, 48):
    print(f"  next {bars:2d} bars: reverse MFE median {f[f'mfe{bars}'].median():+.2f}R  "
          f"mean {f[f'mfe{bars}'].mean():+.2f}R   |  reverse MAE median {f[f'mae{bars}'].median():+.2f}R")
print(f"  price returned through the entry level within 24 bars: {100*f.back_through_level.mean():.0f}%")
f.to_csv(R + r"\loss_after_stop.csv", index=False)
