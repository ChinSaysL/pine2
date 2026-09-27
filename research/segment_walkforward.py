"""Walk-forward test of 'filter the losing parts of the market'.
Losing segments (session / weekday / 2-hour block, by entry time in New York) are chosen on one period
and removed in the other. Does cutting yesterday's losers help tomorrow?"""
import numpy as np
import pandas as pd

t = pd.read_csv("mt5_g_ema0.csv", sep=";")
t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M")
h = t.et.dt.hour
t["session"] = np.where((h >= 18) | (h < 3), "Asia", np.where(h < 8, "London", "New York"))
t["weekday"] = t.et.dt.day_name().str[:3]
t["hour2"] = (h // 2 * 2).astype(str).str.zfill(2) + "h"
t["period"] = np.where(t.et.dt.year >= 2025, "B", "A")        # A = Sep 2022 - 2024, B = 2025 - 2026

for seg in ("session", "weekday", "hour2"):
    for train, test in (("A", "B"), ("B", "A")):
        tr = t[t.period == train].groupby(seg).r.sum()
        losers = list(tr[tr < 0].index)
        te = t[t.period == test]
        kept = te[~te[seg].isin(losers)]
        cut = te[te[seg].isin(losers)]
        names = {"A": "2022-24", "B": "2025-26"}
        print(f"{seg:8s} losers picked on {names[train]}: {', '.join(losers) if losers else 'none':38s} -> "
              f"in {names[test]} those made {cut.r.sum():+6.1f}R; result {te.r.sum():+6.1f}R -> {kept.r.sum():+6.1f}R "
              f"({'HELPED' if kept.r.sum() > te.r.sum() else 'HURT'})")
