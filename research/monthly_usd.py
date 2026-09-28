import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import stats_summary as S
S.T, S.D = 8.0, 2.5                                            # live guards since 2026-09-27 13:22 UTC
import final_summary as FS
def month(s):
    S.T, S.D = 8.0, 2.5
    t, ev, days = FS.PREP["x"]
    b, m, w, _, _, pnl, lo = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(start=s, pnl=b, worst_day=w, low=lo)
if __name__ == "__main__":
    FS.init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=FS.init) as p: mo = pd.DataFrame(p.map(month, months))
    mo["y"] = mo.start.dt.tz_convert("Europe/Prague").dt.year
    x = mo.pnl
    print(f"months {len(x)} | avg {x.mean():+.2f}% | median {x.median():+.2f}% | positive {(x > 0).mean():.0%} | 10th {x.quantile(.1):+.2f}% | 90th {x.quantile(.9):+.2f}% | worst {x.min():+.2f}% | best {x.max():+.2f}% | worst day {mo.worst_day.min():+.2f}% | lowest {mo.low.min():+.2f}%")
    print("avg by year %:", mo.groupby("y").pnl.mean().round(2).to_dict())
    print("2026 avg %:", round(mo[mo.y == 2026].pnl.mean(), 2), "| 2024-26 avg %:", round(mo[mo.y >= 2024].pnl.mean(), 2), "| 2021-23 avg %:", round(mo[mo.y <= 2023].pnl.mean(), 2))
