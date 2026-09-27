"""Real-time regime filter from the strategy's own recent results ("shadow trading").
Every signal is still tracked on paper; a trade is taken for real only if the paper results of the
trades that CLOSED before it opened (last N trades, or last D days) are positive. No look-ahead."""
import numpy as np
import pandas as pd

t = pd.read_csv("mt5_g_ema0.csv", sep=";")
t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M")
t["xt"] = pd.to_datetime(t.exit_time_ny, format="%Y.%m.%d %H:%M")
t = t.sort_values("et").reset_index(drop=True)


def filtered(rule, n):
    take = []
    for i, row in t.iterrows():
        past = t[t.xt <= row.et]                     # only trades already closed
        if rule == "trades":
            window = past.tail(n)
        else:
            window = past[past.xt >= row.et - pd.Timedelta(days=n)]
        take.append(len(window) < 5 or window.r.sum() > 0)   # warm-up: trade until there is history
    return t[np.array(take)]


def stats(x, label):
    r = x.r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    y = x.groupby(x.xt.dt.year).r.sum()
    yrs = " ".join(f"{k}:{y.get(k, 0):+6.1f}" for k in (2022, 2023, 2024, 2025, 2026))
    print(f"{label:28s} {len(r):4d} trades {r.sum():+7.1f}R  PF {r[r > 0].sum() / -r[r < 0].sum():.2f}  "
          f"maxDD {np.max(np.maximum.accumulate(cum) - cum):5.1f}R   {yrs}")


stats(t, "no regime filter")
for n in (20, 30, 50):
    stats(filtered("trades", n), f"last {n} trades positive")
for d in (30, 60, 90):
    stats(filtered("days", d), f"last {d} days positive")
