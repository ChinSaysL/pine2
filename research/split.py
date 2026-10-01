"""Per-strategy contribution inside the CURRENT combined config (gold v2 + Nasdaq 0.75x), calendar months, fresh account."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import stats_summary as S
from current_odds import init, PREP

def month(s):
    t, ev, days = PREP["x"]
    nxt = s + pd.offsets.MonthBegin(1)
    b, m, w, _, _, pnl, lo = S.sim(t, ev, days, s, (nxt - s).days)
    g = [x for k, x in pnl if k == "gold"]; n = [x for k, x in pnl if k == "nasdaq"]
    return dict(start=s, total=b, gold=sum(g), nasdaq=sum(n), gold_n=len(g), nq_n=len(n),
                gold_w=sum(x > 0 for x in g), nq_w=sum(x > 0 for x in n))

if __name__ == "__main__":
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        r = pd.DataFrame(p.map(month, months))
    r["y"] = r.start.dt.year
    print("PER MONTH (average over 60 months):")
    for k, n, w in (("gold", "gold_n", "gold_w"), ("nasdaq", "nq_n", "nq_w")):
        print(f"  {k:7s} avg {r[k].mean():+.2f}% / month | median {r[k].median():+.2f}% | positive months {(r[k] > 0).mean():.0%} | "
              f"trades/month {r[n].mean():.1f} | trade win rate {r[w].sum() / max(r[n].sum(), 1):.0%} | total {r[k].sum():+.1f}%")
    print(f"  COMBINED avg {r.total.mean():+.2f}% / month | positive months {(r.total > 0).mean():.0%}")
    print("  months where gold lost but Nasdaq made money:", int(((r.gold < 0) & (r.nasdaq > 0)).sum()), "of", int((r.gold < 0).sum()), "losing gold months")
    print("  months where Nasdaq lost but gold made money:", int(((r.nasdaq < 0) & (r.gold > 0)).sum()), "of", int((r.nasdaq < 0).sum()), "losing Nasdaq months")
    print("\nBY YEAR (sum of fresh months, %):")
    print(r.groupby("y")[["gold", "nasdaq", "total"]].sum().round(1).to_string())
    print("\nLAST 12 MONTHS:")
    x = r.tail(12).copy(); x["month"] = x.start.dt.strftime("%Y-%m")
    print(x[["month", "gold", "nasdaq", "total", "gold_n", "nq_n"]].round(1).to_string(index=False))
