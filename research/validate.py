"""Score logic variants on 15m (Apr-Sep 2026) and on 30m / 1H gold (Jan 2025 - Sep 2026).

Out of sample (OOS) = Jan 2025 - Mar 2026: never seen by any tuning of this strategy.
"""
import sys
import numpy as np
import pandas as pd
from engine import load, run

d = sys.argv[1] if len(sys.argv) > 1 else "."
data = {tf: load(f"{d}/bars{tf}_raw.txt") for tf in ("15", "30", "60")}


def score(t):
    if len(t) == 0:
        return dict(n=0, total=0, pf=0, dd=0)
    r = t.r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    return dict(n=len(r), total=round(r.sum(), 1), pf=round(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), 2),
                dd=round(np.max(np.maximum.accumulate(cum) - cum), 1))


def periods(t):
    et = pd.to_datetime(t.entry_time)
    et = et.dt.tz_localize("UTC") if et.dt.tz is None else et
    q = et.dt.year.astype(str) + "H" + np.where(et.dt.month <= 6, "1", "2")
    return t.groupby(q.values).r.sum().round(1).to_dict()


def evaluate(name, variants):
    print(f"\n##### {name}")
    for label, kw in variants.items():
        line = f"{label:34s}"
        for tf, df in data.items():
            t = run(df, **kw)
            if tf == "15":
                s = score(t)
                line += f" | 15m: {s['n']:3d}tr {s['total']:+6.1f}R pf{s['pf']:.2f} dd{s['dd']:4.1f}"
            else:
                et = pd.to_datetime(t.entry_time)
                et = et.dt.tz_localize("UTC") if et.dt.tz is None else et
                oos = t[et < pd.Timestamp("2026-04-01", tz="UTC")]
                rec = t[et >= pd.Timestamp("2026-04-01", tz="UTC")]
                so, sr = score(oos), score(rec)
                line += f" | {tf}m OOS: {so['n']:3d}tr {so['total']:+6.1f}R pf{so['pf']:.2f} dd{so['dd']:4.1f}  recent {sr['total']:+6.1f}R"
        print(line)


if __name__ == "__main__":
    evaluate("current logic", {"current": {}})
    for tf in ("30", "60"):
        print(f"{tf}m half-years (current):", periods(run(data[tf])))
