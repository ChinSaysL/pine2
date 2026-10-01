"""Focused comparison: the live exit vs protection that only kicks in late in the day
(the pattern from the 2026-09-30 challenge trade: up ~1R in the morning, negative at the close).
Uses the loader/simulators from nq_exits.py."""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import nq_exits as X

RULES = {
    "live: fixed stop -> 15:55":                dict(),
    "afternoon: BE at 13:00 if >= +0.5R":       dict(be_at=780, be_at_min=0.5),
    "afternoon: BE at 14:00 if >= +0.5R":       dict(be_at=840, be_at_min=0.5),
    "afternoon BE 13:00 + trail 0.5R at +1.5R": dict(be_at=780, be_at_min=0.5, trail_after=1.5, trail=0.5),
    "afternoon: BE at 13:00 if >= +0.25R":      dict(be_at=780, be_at_min=0.25),
}

days, D, cost = X.load_days()
keys = list(days)
rows = []
for i, day in enumerate(keys):
    x = days[day]
    s = X.orb_setup(x, D, day)
    if s:
        dr, e, st, k0 = s
        pk = X.peak_r(x, k0, dr, e, st)
        for name, rule in RULES.items():
            r = X.walk(x, k0, dr, e, st, cost, rule)
            if r:
                rows.append(dict(day=day, stream="ORB", rule=name, r=r[0], peak=pk, hm=r[1]))
    n = X.noise_entry(days, keys, i, D)
    if n:
        dr, e, st, k0, lvl = n
        pk = X.peak_r(x, k0, dr, e, st, lvl)
        for name, rule in RULES.items():
            r = X.walk(x, k0, dr, e, st, cost, rule, lvl)
            if r:
                rows.append(dict(day=day, stream="NOISE", rule=name, r=r[0], peak=pk, hm=r[1]))

t = pd.DataFrame(rows)
t["year"] = pd.to_datetime(t.day).dt.year
f = open("nq_exits_afternoon.txt", "w", encoding="utf-8")

def emit(s=""):
    print(s, flush=True)
    f.write(s + "\n")
    f.flush()

emit(f"sessions {len(days)}  {min(days)} .. {max(days)}")
for stream in ("ORB", "NOISE", "BOTH"):
    u = t if stream == "BOTH" else t[t.stream == stream]
    agg = u.groupby("rule").apply(lambda g: pd.Series({
        "n": len(g), "totR": g.r.sum(),
        "PF": g.r[g.r > 0].sum() / max(-g.r[g.r < 0].sum(), 1e-9),
        "win%": (g.r > 0).mean() * 100,
        "gave_back%": ((g.peak >= 0.5) & (g.r < 0)).mean() * 100,
        "2026R": g[g.year == 2026].r.sum(),
        "R minexit": g[g.r < 0].r.min() if (g.r < 0).any() else 0,
    }), include_groups=False).reindex(list(RULES))
    emit(f"\n===== {stream} stream ({len(u) // len(RULES)} trades) =====")
    emit(agg.round(2).to_string())
piv = t.pivot_table(index="rule", columns="year", values="r", aggfunc="sum").round(1)
emit("\n===== R per year, both streams =====")
emit(piv.to_string())
f.close()

