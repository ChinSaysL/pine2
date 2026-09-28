"""FTMO pass odds for the CURRENT live config: gold v2 (BAD = half risk, cap 1.25%, guards 7/3.5) + Nasdaq always on
at 0.75x, Fed days skipped. Split by gold's regime at the challenge start. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from portfolio import nasdaq_all
from third_combo import gold_bad_at

PREP = {}
def init():
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    t = pd.concat([g, nasdaq_all().assign(w=0.75)]).sort_values("entry_time").reset_index(drop=True)
    PREP["x"] = (t,) + F.prepare(t)[1:]

def job(s):
    t, ev, days = PREP["x"]; out = {"start": s}
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"low{h}"] = p, st, lo
    return out

if __name__ == "__main__":
    init()
    with Pool(14, initializer=init) as p:
        r = pd.DataFrame(p.map(job, S.STARTS, chunksize=20))
    r["bad"] = gold_bad_at(pd.Series(r.start).dt.tz_convert("UTC"))
    r["era"] = np.where(r.start < pd.Timestamp("2024-01-01", tz="UTC"), "gold ranging 2021-23", "gold trending 2024-26")
    def row(x, lab):
        return {"starts": lab, "n": len(x), **{f"pass {h}d": f"{x[f'pass{h}'].mean():.0%}" for h in (30, 60, 90)},
                "stuck 90d": f"{x.stuck90.mean():.0%}", "lowest vs start (worst)": f"{x.low90.min():+.1f}%"}
    rows = [row(r, "ALL start days 2021-10..2026-06"), row(r[~r.bad], "gold GOOD regime at start"), row(r[r.bad], "gold BAD regime at start (like Thursday)")]
    for e, x in r.groupby("era"):
        rows.append(row(x, e)); rows.append(row(x[x.bad], f"   {e}, BAD at start"))
    print(pd.DataFrame(rows).to_string(index=False))
