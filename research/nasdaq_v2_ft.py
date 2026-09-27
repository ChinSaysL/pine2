import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import pandas as pd
import nasdaq_v2 as N
if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(N.job, [("ft", g) for g in N.GRID])
    rows = []
    for src, W, ex, rv, dj, t in res:
        t["y"] = [x.year for x in t.date]
        pf = t.r[t.r > 0].sum() / max(-t.r[t.r < 0].sum(), 1e-9)
        row = dict(W=W, exit=ex, rvol=rv, doji=dj, total=round(t.r.sum(), 1), n=len(t), PF=round(pf, 2))
        row.update(t.groupby("y").r.sum().round(1).to_dict()); rows.append(row)
    pd.set_option("display.width", 250); print(pd.DataFrame(rows).to_string(index=False))
