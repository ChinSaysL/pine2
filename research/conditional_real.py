"""Simpler live version: the regime is judged from the bot's REAL closed trades only (no paper trading).
In a bad regime (real results over the last N days negative) only New York entries are taken, so the
regime can only recover through New York trades - this checks that it still works."""
import warnings
import numpy as np
import pandas as pd
from ftmo_sim2 import prepare, run_challenge, scaled
import conditional_filter as cf

warnings.filterwarnings("ignore")
t = cf.t.sort_values("et").reset_index(drop=True)


def real_only(days):
    kept = []            # indexes of trades actually taken
    for i, row in t.iterrows():
        past = t.loc[kept]
        past = past[(past.xt <= row.et) & (past.xt >= row.et - pd.Timedelta(days=days))]
        bad = len(past) >= 3 and past.r.sum() < 0
        if not bad or row.session == "New York":
            kept.append(i)
    return t.loc[kept]


def utc(df):
    o = df.copy()
    o["entry_time"] = o.et.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    o["exit_time"] = o.xt.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    return o.dropna(subset=["entry_time", "exit_time"])[["entry_time", "exit_time", "r"]]


fn = scaled(1.25, 4, int_total=5.0)
for name, lst in [("no filter", t)] + [(f"real {d}d bad -> NY only", real_only(d)) for d in (30, 60, 90)]:
    r = lst.r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    y = lst.groupby(lst.xt.dt.year).r.sum()
    head = (f"{name:24s} {len(r):4d} trades {r.sum():+7.1f}R maxDD {np.max(np.maximum.accumulate(cum) - cum):5.1f}R  "
            + " ".join(f"{k}:{y.get(k, 0):+.0f}" for k in (2022, 2023, 2024, 2025, 2026)))
    tt, ev, days = prepare(utc(lst))
    first = pd.Timestamp("2022-10-01", tz="Europe/Prague")
    last = tt.exit_time.max().tz_convert("Europe/Prague").normalize()
    out = []
    for lab, a, b in [("22-23", "2022-10-01", "2024-01-01"), ("2024", "2024-01-01", "2025-01-01"), ("25-26", "2025-01-01", "2027-01-01")]:
        rr = {}
        for hz in (30, 90):
            st = [first + pd.Timedelta(days=i) for i in range(0, (last - first).days - hz + 1)]
            st = [s for s in st if s.weekday() < 5 and pd.Timestamp(a, tz="Europe/Prague") <= s < pd.Timestamp(b, tz="Europe/Prague")]
            res = [run_challenge(tt, ev, days, s, fn, horizon_days=hz, int_total=5.0, int_daily=2.5) for s in st]
            rr[hz] = (np.mean([x[0] == "pass" for x in res]), np.mean([x[0] == "fail" for x in res]))
        out.append(f"{lab} {rr[30][0]:3.0%}/{rr[90][0]:3.0%}/stuck {rr[90][1]:3.0%}")
    print(head + "\n      " + " | ".join(out))
