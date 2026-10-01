"""Summary of the DEPLOYED system (2026-09-27): gold EA v2 (FTMO tester, news 30/30, BAD = half risk) + Nasdaq EA v3
(FTMO tester: opening trade with the indecisive-candle filter + noise engine, 0.75x each). Live policy: cap 1.25%,
divisor 4, guards 7% / 3.5%. Fresh account from every start day, Oct 2021 - Sep 2026. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from third_combo import gold_bad_at

ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")


def book():
    g = pd.read_csv("mt5_gold_news_30_30.csv", sep=";")
    g["entry_time"], g["exit_time"] = ny(g.entry_time_ny), ny(g.exit_time_ny)
    g = g.dropna(subset=["entry_time", "exit_time"])
    g["w"] = np.where(gold_bad_at(g.entry_time), 0.5, 1.0); g["stop"] = g.r < -0.5; g["mkt"] = "gold"
    n = pd.read_csv("mt5_nq_body.csv", sep=";")
    n["entry_time"], n["exit_time"] = ny(n.entry_time_ny), ny(n.exit_time_ny)
    n = n.dropna(subset=["entry_time", "exit_time"])
    n["w"] = 0.75; n["stop"] = n.r < -0.5; n["mkt"] = np.where(n.comment.str.contains("NOISE"), "nasdaq noise", "nasdaq opening")
    cols = ["entry_time", "exit_time", "r", "w", "stop", "mkt"]
    return pd.concat([g[cols], n[cols]]).sort_values("entry_time").reset_index(drop=True)


PREP = {}
def init():
    t = book(); PREP["x"] = (t,) + F.prepare(t)[1:]


def job(s):
    t, ev, days = PREP["x"]; out = {"start": s}
    for h in (1, 7, 30):
        b, m, w, _, _, _, lo = S.sim(t, ev, days, s, h)
        out[f"p{h}"], out[f"dd{h}"], out[f"low{h}"] = b, m, lo
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"clow{h}"], out[f"cwd{h}"], out[f"cdd{h}"] = p, st, lo, w, m
    return out


def month(s):
    t, ev, days = PREP["x"]
    b, m, w, _, _, pnl, lo = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    out = dict(start=s, total=b, worst_day=w, low=lo)
    for k in ("gold", "nasdaq opening", "nasdaq noise"): out[k] = sum(x for mk, x in pnl if mk == k)
    return out


if __name__ == "__main__":
    init()
    t = PREP["x"][0]
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        r = pd.DataFrame(p.map(job, S.STARTS, chunksize=20)); mo = pd.DataFrame(p.map(month, months))
    r["bad"] = gold_bad_at(pd.Series(r.start).dt.tz_convert("UTC"))
    r["era"] = np.where(r.start < pd.Timestamp("2024-01-01", tz="UTC"), "2021-23", "2024-26")
    r.to_pickle("final_summary.pkl"); mo.to_pickle("final_months.pkl")
    print("TRADES (Oct 2021 - Sep 2026):")
    for k, x in t.groupby("mkt"):
        print(f"  {k:15s} {len(x):5d} trades | win rate {100 * (x.r > 0).mean():.1f}% | avg {x.r.mean():+.3f}R | PF {x.r[x.r > 0].sum() / -x.r[x.r < 0].sum():.2f}")
    tt = t.assign(d=t.exit_time.dt.tz_convert("Europe/Prague").dt.date).groupby("d").apply(lambda x: (x.r * x.w).sum())
    print(f"  winning trading days: {100 * (tt > 0).mean():.1f}% of {len(tt)}")
    for h in (1, 7, 30):
        x = r[f"p{h}"]
        print(f"\n{h}-DAY P&L %: avg {x.mean():+.2f} | median {x.median():+.2f} | 10th {x.quantile(.1):+.2f} | 90th {x.quantile(.9):+.2f} | positive {(x > 0).mean():.0%} | "
              f"worst {x.min():+.2f} | best {x.max():+.2f} | lowest vs start: median {r[f'low{h}'].median():+.2f}, worst {r[f'low{h}'].min():+.2f}")
        print("   avg by era:", r.groupby("era")[f"p{h}"].mean().round(2).to_dict(), "| gold-BAD starts avg:", round(float(r[r.bad][f"p{h}"].mean()), 2))
    print()
    for h in (30, 60, 90):
        print(f"PASS within {h}d: all {r[f'pass{h}'].mean():.1%} | gold GOOD start {r[~r.bad][f'pass{h}'].mean():.1%} | gold BAD start {r[r.bad][f'pass{h}'].mean():.1%} | "
              f"2021-23 {r[r.era == '2021-23'][f'pass{h}'].mean():.1%} | 2024-26 {r[r.era == '2024-26'][f'pass{h}'].mean():.1%} | stuck {r[f'stuck{h}'].mean():.1%} | "
              f"lowest vs start: median {r[f'clow{h}'].median():+.2f}% 5th {r[f'clow{h}'].quantile(.05):+.2f}% worst {r[f'clow{h}'].min():+.2f}% | worst day {r[f'cwd{h}'].min():+.2f}% | "
              f"peak-to-trough median {r[f'cdd{h}'].median():.2f}% worst {r[f'cdd{h}'].max():.2f}%")
    mo["y"] = mo.start.dt.tz_convert("Europe/Prague").dt.year; mo["m"] = mo.start.dt.tz_convert("Europe/Prague").dt.month
    print(f"\nCALENDAR MONTHS (fresh account): avg {mo.total.mean():+.2f}% | median {mo.total.median():+.2f}% | positive {(mo.total > 0).mean():.0%} | "
          f">= +10%: {(mo.total >= 10).mean():.0%} | <= -5%: {(mo.total <= -5).mean():.0%} | worst {mo.total.min():+.2f}% | best {mo.total.max():+.2f}%")
    print(mo.pivot_table(index="y", columns="m", values="total").round(1).to_string())
    print("\nBY YEAR (sum of fresh months, %):"); print(mo.groupby("y")[["gold", "nasdaq opening", "nasdaq noise", "total"]].sum().round(1).to_string())
    print("\nPER MONTH AVERAGE BY STRATEGY:", mo[["gold", "nasdaq opening", "nasdaq noise", "total"]].mean().round(2).to_dict())
