"""Regime-filter variants on 4 years of FTMO gold data: yearly R and challenge pass rates by start period."""
import sys
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
NAMES = sys.argv[1:] or ["g_base", "g_adx18", "g_adx20", "g_adx22", "g_adx25", "g_ema0", "g_ema2", "g_ema4", "g_adx22ema0"]


def load(name):
    t = pd.read_csv(f"mt5_{name}.csv", sep=";")
    for c in ("entry", "exit"):
        t[f"{c}_time"] = (pd.to_datetime(t[f"{c}_time_ny"], format="%Y.%m.%d %H:%M")
                          .dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC"))
    return t.dropna(subset=["entry_time", "exit_time"])


def passes(name):
    from ftmo_sim2 import prepare, run_challenge, scaled
    t = load(name)[["entry_time", "exit_time", "r"]]
    tt, ev, days = prepare(t)
    first = pd.Timestamp("2022-10-01", tz="Europe/Prague")
    last = tt.exit_time.max().tz_convert("Europe/Prague").normalize()
    fn = scaled(1.25, 4, int_total=5.0)
    out = {}
    for label, a, b in [("22-23", "2022-10-01", "2024-01-01"), ("2024", "2024-01-01", "2025-01-01"), ("25-26", "2025-01-01", "2027-01-01")]:
        for hz in (30, 90):
            starts = [first + pd.Timedelta(days=i) for i in range(0, (last - first).days - hz + 1)]
            starts = [s for s in starts if s.weekday() < 5 and pd.Timestamp(a, tz="Europe/Prague") <= s < pd.Timestamp(b, tz="Europe/Prague")]
            res = [run_challenge(tt, ev, days, s, fn, horizon_days=hz, int_total=5.0, int_daily=2.5) for s in starts]
            out[f"{label} pass{hz}"] = np.mean([x[0] == "pass" for x in res])
            if hz == 90:
                out[f"{label} stuck"] = np.mean([x[0] == "fail" for x in res])
    return name, out


if __name__ == "__main__":
    rows = []
    for n in NAMES:
        t = load(n)
        r = t.r.values
        cum = np.concatenate([[0], np.cumsum(r)])
        row = dict(variant=n, pos=len(r), R=round(r.sum(), 1), PF=round(r[r > 0].sum() / -r[r < 0].sum(), 2),
                   maxDD=round(np.max(np.maximum.accumulate(cum) - cum), 1))
        y = t.groupby(t.exit_time.dt.year).r.sum()
        for yr in (2022, 2023, 2024, 2025, 2026):
            row[str(yr)] = round(y.get(yr, 0.0), 1)
        rows.append(row)
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))
    with Pool(min(14, len(NAMES))) as pool:
        pr = dict(pool.map(passes, NAMES))
    P = pd.DataFrame(pr).T
    print("\nChallenge pass rates with the live risk settings (scaled 1.25%, guards 5%/2.5%), by start period:")
    print(P.map(lambda v: f"{v:.0%}").to_string())
