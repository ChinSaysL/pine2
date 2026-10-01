"""Conditional filter: in a detected bad regime, trade only the segments that hold up in bad regimes.
Bad regime (real time): paper results of trades that CLOSED in the previous N days are negative."""
import sys
import numpy as np
import pandas as pd

t = pd.read_csv("mt5_g_ema0.csv", sep=";")
t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M")
t["xt"] = pd.to_datetime(t.exit_time_ny, format="%Y.%m.%d %H:%M")
t = t.sort_values("et").reset_index(drop=True)
h = t.et.dt.hour
t["session"] = np.where((h >= 18) | (h < 3), "Asia", np.where(h < 8, "London", "New York"))
t["period"] = np.where(t.et.dt.year >= 2025, "2025-26", "2022-24")


def regime(days):
    flags = []
    for _, row in t.iterrows():
        past = t[(t.xt <= row.et) & (t.xt >= row.et - pd.Timedelta(days=days))]
        flags.append("bad" if len(past) >= 5 and past.r.sum() < 0 else "good")
    return np.array(flags)


for days in (30, 60, 90):
    t["regime"] = regime(days)
    print(f"\n=== bad regime = last {days} days of paper results negative")
    tab = t.pivot_table(index=["regime", "session"], columns="period", values="r", aggfunc=["count", "sum", "mean"]).round(2)
    print(tab.to_string())
    # the rule: in a bad regime trade only New York; otherwise everything
    keep = (t.regime == "good") | (t.session == "New York")
    for p in ("2022-24", "2025-26"):
        a, b = t[t.period == p].r.sum(), t[(t.period == p) & keep].r.sum()
        print(f"  rule 'bad regime -> New York only' in {p}: {a:+.1f}R -> {b:+.1f}R")
    r = t[keep].r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    r0 = t.r.values
    c0 = np.concatenate([[0], np.cumsum(r0)])
    print(f"  4 years: {r0.sum():+.1f}R maxDD {np.max(np.maximum.accumulate(c0) - c0):.1f}R  ->  {r.sum():+.1f}R maxDD {np.max(np.maximum.accumulate(cum) - cum):.1f}R")
t.to_pickle("conditional_trades.pkl")
