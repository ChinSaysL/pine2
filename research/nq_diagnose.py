"""Why does the Nasdaq opening trade lose in 2026? Features of every ORB trade (FTMO M5), R per trade by bucket and era.
Looking for a cause that ALSO hurt in earlier years (a real rule), not a 2026-only pattern."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from nq_logic import load

days, D, cost = load()
D["atr_pct"] = D.atr / D.c.shift(1) * 100
D["atr_pct_rank"] = D.atr_pct.rolling(250, min_periods=60).apply(lambda s: (s.iloc[-1] >= s).mean(), raw=False)
D["ret20"] = D.c.pct_change(20).shift(1) * 100
rows = []
for day, x in days.items():
    a = D.atr[day]
    if np.isnan(a): continue
    f = x.iloc[:3]; o0, c0, hi, lo = f.o.iat[0], f.c.iat[-1], f.h.max(), f.l.min()
    if c0 == o0: continue
    dr = 1 if c0 > o0 else -1
    rest = x.iloc[3:]; e = rest.o.iat[0]
    st = lo if dr == 1 else hi; floor_used = (e - st) * dr < 0.3 * a
    if floor_used: st = e - dr * 0.3 * a
    R = (e - st) * dr; px = None; mfe = 0.0; t_exit = None
    for b in rest.itertuples():
        if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px, t_exit = st, b.hm; break
        mfe = max(mfe, ((b.h - e) if dr == 1 else (e - b.l)) / R)
        if b.hm >= 955: px, t_exit = b.c, b.hm; break
    if px is None: px, t_exit = rest.c.iat[-1], 955
    pc = D.pc[day]
    rows.append(dict(day=pd.Timestamp(day), r=((px - e) * dr - cost) / R, dir="long" if dr == 1 else "short",
                     or_atr=(hi - lo) / a, floor=floor_used, gap_atr=(o0 - pc) / a if not np.isnan(pc) else np.nan,
                     body_frac=abs(c0 - o0) / (hi - lo), atr_pct=D.atr_pct[day], vol_rank=D.atr_pct_rank[day],
                     trend20=D.ret20[day], mfe=mfe, stopped=px == st, stop_time=t_exit, wd=pd.Timestamp(day).day_name()[:3]))
t = pd.DataFrame(rows)
t["era"] = np.select([t.day < "2024-01-01", t.day < "2026-01-01"], ["2021-23", "2024-25"], "2026")
t["with_trend20"] = np.sign(t.trend20) == np.where(t.dir == "long", 1, -1)
t["gap_agrees"] = np.sign(t.gap_atr) == np.where(t.dir == "long", 1, -1)
t.to_pickle("nq_diag.pkl")
pd.set_option("display.width", 250)


def table(col, bins=None, labels=None):
    x = t.copy()
    if bins is not None: x[col] = pd.cut(x[col], bins, labels=labels)
    g = x.groupby([col, "era"]).r.agg(["mean", "count", "sum"]).round(2).unstack("era")
    print(f"\n=== {col} (avg R per trade | trades | total R)"); print(g.to_string())


print("ERA totals:", t.groupby("era").r.agg(["mean", "count", "sum"]).round(2).to_dict("index"))
table("dir")
table("vol_rank", [0, .25, .5, .75, 1.01], ["vol low 25%", "vol 25-50%", "vol 50-75%", "vol high 25%"])
table("or_atr", [0, .15, .25, .4, 5], ["OR <0.15 ATR", "OR .15-.25", "OR .25-.40", "OR >0.40"])
table("gap_atr", [-9, -.5, -.1, .1, .5, 9], ["gap < -0.5", "-0.5..-0.1", "flat", "0.1..0.5", "gap > 0.5"])
table("body_frac", [0, .3, .6, 1.01], ["body <30%", "30-60%", ">60%"])
table("with_trend20")
table("floor")
table("wd")
print("\nMFE of trades that ended stopped out (how far they went in favour first), by era:")
print(t[t.stopped].groupby("era").mfe.describe(percentiles=[.25, .5, .75]).round(2).to_string())
print("\nshare of trades stopped before 11:00 NY:", t.assign(early=t.stopped & (t.stop_time < 660)).groupby("era").early.mean().round(2).to_dict())
print("share of big winners (>= +2R):", t.assign(big=t.r >= 2).groupby("era").big.mean().round(3).to_dict())
