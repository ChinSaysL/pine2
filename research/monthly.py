"""Monthly profit of the CURRENT config (gold v2 + Nasdaq 0.75x always, Fed days skipped), fresh account each month,
no stop at +10%. Calendar months and rolling 30-day windows; split by era and by gold regime at the start. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from current_odds import init, PREP
from third_combo import gold_bad_at

def month(s):
    t, ev, days = PREP["x"]
    nxt = (s + pd.offsets.MonthBegin(1))
    b, m, w, _, _, _, lo = S.sim(t, ev, days, s, (nxt - s).days)
    return dict(start=s, pnl=b, dd=m, low=lo, worst_day=w)

def win30(s):
    t, ev, days = PREP["x"]
    b, m, w, _, _, _, lo = S.sim(t, ev, days, s, 30)
    return dict(start=s, pnl=b)

if __name__ == "__main__":
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        cm = pd.DataFrame(p.map(month, months)); rw = pd.DataFrame(p.map(win30, S.STARTS, chunksize=20))
    for x in (cm, rw):
        x["bad"] = gold_bad_at(pd.Series(x.start).dt.tz_convert("UTC"))
        x["era"] = np.where(x.start < pd.Timestamp("2024-01-01", tz="UTC"), "2021-23 (gold ranging)", "2024-26 (gold trending)")
    def stats(v): return f"avg {v.mean():+5.2f}% | median {v.median():+5.2f}% | 10th {v.quantile(.1):+5.2f}% | 90th {v.quantile(.9):+5.2f}% | positive {(v > 0).mean():4.0%} | worst {v.min():+5.2f}% | best {v.max():+5.2f}%"
    print("CALENDAR MONTHS (fresh account each month):", len(cm))
    print("  all          ", stats(cm.pnl))
    for e, x in cm.groupby("era"): print(f"  {e:24s}", stats(x.pnl))
    print("  BAD at start ", stats(cm.pnl[cm.bad]), "| n", cm.bad.sum())
    print("  months >= +10%:", f"{(cm.pnl >= 10).mean():.0%}", "| months <= -5%:", f"{(cm.pnl <= -5).mean():.0%}", "| worst day in any month", f"{cm.worst_day.min():+.2f}%")
    print("\nROLLING 30-DAY WINDOWS (every start day):", len(rw))
    print("  all          ", stats(rw.pnl))
    print("  BAD at start ", stats(rw.pnl[rw.bad]))
    print("\nCALENDAR MONTH P&L % by year:")
    cm["y"], cm["m"] = cm.start.dt.year, cm.start.dt.month
    print(cm.pivot_table(index="y", columns="m", values="pnl").round(1).to_string())
    print("year total (sum of fresh months):", cm.groupby("y").pnl.sum().round(1).to_dict())
