"""ORB-only exit experiment (fast): live exit vs protection that only starts late in the day.
Targets the 2026-09-30 pattern: the opening-range trade is up ~1R in the morning and closes
negative at 15:55. Writes nq_orb_exits.txt next to this file."""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import nq_exits as X

RULES = {
    "live":                                 dict(),
    "afterBE13":                            dict(be_at=780, be_at_min=0.5),
    "afterBE14":                            dict(be_at=840, be_at_min=0.5),
    "afterBE13+trail0.5@1.5":               dict(be_at=780, be_at_min=0.5, trail_after=1.5, trail=0.5),
    "BE0.5":                                dict(be=0.5),
    "trail0.5@1":                           dict(trail_after=1.0, trail=0.5),
    "TP1":                                  dict(tp=1.0),
}

days, D, cost = X.load_days()
rows = []
for day, x in days.items():
    s = X.orb_setup(x, D, day)
    if not s:
        continue
    dr, e, st, k0 = s
    pk = X.peak_r(x, k0, dr, e, st)
    for name, rule in RULES.items():
        r = X.walk(x, k0, dr, e, st, cost, rule)
        if r:
            rows.append(dict(day=day, rule=name, r=r[0], peak=pk, hm=r[1]))

t = pd.DataFrame(rows)
t["year"] = pd.to_datetime(t.day).dt.year
agg = t.groupby("rule").apply(lambda g: pd.Series({
    "n": len(g), "totR": g.r.sum(),
    "PF": g.r[g.r > 0].sum() / max(-g.r[g.r < 0].sum(), 1e-9),
    "win%": (g.r > 0).mean() * 100,
    "gave_back%": ((g.peak >= 0.5) & (g.r < 0)).mean() * 100,
}), include_groups=False).reindex(list(RULES))
piv = t.pivot_table(index="rule", columns="year", values="r", aggfunc="sum").round(1).reindex(list(RULES))
out = ["ORB only, 2021-09..2026-09, FTMO US100.cash M5",
       agg.round(2).to_string(), "", "R by year:", piv.to_string()]
txt = "\n".join(out)
with open("nq_orb_exits.txt", "w", encoding="utf-8") as f:
    f.write(txt)
print(txt)
