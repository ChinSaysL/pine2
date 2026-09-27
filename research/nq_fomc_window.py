"""Nasdaq ORB on Fed (FOMC) days: skip the day vs flat 30 min around the 14:00 NY statement (with/without re-entry)."""
import numpy as np, pandas as pd
from indices import load, daily
from newfam import FOMC
d, cost = load("US100.cash"); D = daily(d); fomc = {pd.Timestamp(x).date() for x in FOMC}
out = []
for day, x in d[(d.hm >= 570) & (d.hm < 960)].groupby("date"):
    if day not in D.index or len(x) < 20 or x.hm.iloc[0] != 570 or day not in fomc: continue
    o0, c0, hi, lo = x.o.iloc[0], x.c.iloc[0], x.h.iloc[0], x.l.iloc[0]; a = D.atr[day]
    if c0 == o0 or np.isnan(a): continue
    dr = 1 if c0 > o0 else -1; rest = x.iloc[1:]; e = rest.o.iloc[0]
    st = lo if dr == 1 else hi
    if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
    risk = (e - st) * dr
    def walk(bars, entry, stop_px, exit_hm):
        for b in bars.itertuples():
            if (dr == 1 and b.l <= stop_px) or (dr == -1 and b.h >= stop_px): return (stop_px - entry) * dr, True
            if b.hm >= exit_hm: return (b.o - entry) * dr, False
        return (bars.c.iloc[-1] - entry) * dr, False
    full, _ = walk(rest, e, st, 955)
    pre, stopped = walk(rest[rest.hm < 810 + 15], e, st, 810)          # flat at 13:30 (bar opening 13:30)
    rB = (pre - cost) / risk
    rC = rB
    if not stopped:
        post = rest[rest.hm >= 870]                                      # re-enter 14:30 if still beyond the stop
        if len(post) and ((dr == 1 and post.o.iloc[0] > st) or (dr == -1 and post.o.iloc[0] < st)):
            e2 = post.o.iloc[0]; p2, _ = walk(post, e2, st, 955); rC = rB + (p2 - cost) / risk
    out.append(dict(day=day, full=(full - cost) / risk, B=rB, C=rC))
t = pd.DataFrame(out)
print(f"FOMC days traded: {len(t)}")
print(f"A skip whole day           : 0.0R")
print(f"   (trading the full day    : {t.full.sum():+.1f}R, avg {t.full.mean():+.2f})")
print(f"B flat at 13:30            : {t.B.sum():+.1f}R, avg {t.B.mean():+.2f}, win {100 * (t.B > 0).mean():.0f}%")
print(f"C flat 13:30, back at 14:30: {t.C.sum():+.1f}R, avg {t.C.mean():+.2f}, win {100 * (t.C > 0).mean():.0f}%")
t["y"] = [x.year for x in t.day]
print(t.groupby("y")[["full", "B", "C"]].sum().round(1).to_string())
