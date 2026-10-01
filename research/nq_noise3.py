import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import nq_noise2 as N
VARS = {"BASE (live)": {}, "HOLD to 15:55 (stop fixed)": dict(exit_mode="hold"), "BAND-only exit": dict(exit_mode="band"),
        "CONFIRM (2 checks)": dict(confirm=True), "CONFIRM + HOLD": dict(confirm=True, exit_mode="hold"), "CONFIRM + BAND-only": dict(confirm=True, exit_mode="band")}
def job(n):
    S, keys, D, cost = N.sessions(); t = N.run(S, keys, D, cost, **VARS[n]); t["v"] = n; return t
if __name__ == "__main__":
    with Pool(len(VARS)) as p: T = pd.concat(p.map(job, list(VARS)))
    T["era"] = np.select([T.day < pd.Timestamp("2024-01-01").date(), T.day < pd.Timestamp("2026-01-01").date()], ["2021-23", "2024-25"], "2026")
    T.to_pickle("nq_noise3.pkl")
    rows = []
    for v, t in T.groupby("v", sort=False):
        row = {"variant": v}
        for e, x in t.groupby("era"): row[e] = f"{x.r.sum():+6.1f}R n={len(x):3d} avg {x.r.mean():+.3f}"
        row["total"] = round(t.r.sum(), 1); row["PF"] = round(t.r[t.r > 0].sum() / -t.r[t.r < 0].sum(), 2); row["win%"] = round(100 * (t.r > 0).mean())
        rows.append(row)
    pd.set_option("display.width", 250); print(pd.DataFrame(rows).to_string(index=False))
