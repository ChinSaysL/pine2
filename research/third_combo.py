"""Does USDJPY London breakout improve the deployed system (gold v2 + Nasdaq when gold BAD)? Live risk policy.
Variants: without / always full risk / always half risk / only while gold BAD. JPY stop exits get +0.1R extra
slippage, and a stress run fills violent-bar stops at the bar extreme. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from usdjpy_lb import lb


def jpy(stress):
    t = lb(worst_fill=stress)
    t["exit_time"] = pd.to_datetime(t.exit_time, utc=True)
    t["stop"] = t.r < -0.5
    t["r"] = t.r - np.where(t.stop, 0.1, 0.0)
    t["mkt"] = "usdjpy"
    return t[(t.entry_time >= S.START - pd.Timedelta(days=5))]


def gold_bad_at(times):
    pp = pd.read_csv("paper_bm_halfrisk.csv", sep=";")
    pp["x"] = pd.to_datetime(pp.exit_ny, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    pp = pp.dropna(subset=["x"]).sort_values("x")
    ex = pp.x.values.astype("datetime64[ns]"); cum = np.r_[0, np.cumsum(pp.r.values)]
    e = times.dt.tz_convert(None).values.astype("datetime64[ns]")
    hi = np.searchsorted(ex, e); lo = np.searchsorted(ex, e - np.timedelta64(60, "D"))
    return (hi - lo >= 5) & (cum[hi] - cum[lo] < 0)


PREP = {}
def init():
    base = S.book()
    for stress in (False, True):
        j = jpy(stress); bad = gold_bad_at(j.entry_time)
        tag = " [worst-fill stress]" if stress else ""
        V = {"gold + Nasdaq (deployed)": base,
             "+ USDJPY always, full risk": pd.concat([base, j.assign(w=1.0)]),
             "+ USDJPY always, half risk": pd.concat([base, j.assign(w=0.5)]),
             "+ USDJPY only while gold BAD": pd.concat([base, j[bad].assign(w=1.0)])}
        for k, t in V.items():
            if stress and k.startswith("gold"): continue
            t = t.sort_values("entry_time").reset_index(drop=True)
            PREP[k + tag] = (t,) + F.prepare(t)[1:]


def job(a):
    name, s = a
    t, ev, days = PREP[name]
    out = dict(name=name, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"low{h}"], out[f"wd{h}"] = p, st, lo, w
    b, m, w, _, _, _, lo = S.sim(t, ev, days, s, 30)
    out["p30"] = b
    return out


if __name__ == "__main__":
    init()
    jobs = list(itertools.product(PREP, S.STARTS[::2]))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, jobs, chunksize=20))
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "ranging 21-23", "trending 24-26")
    g = res.groupby("name")
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(),
                        "stuck90": g.stuck90.mean(), "avg 30d %": g.p30.mean(), "lowest vs start (worst)": g.low90.min(),
                        "worst day": g.wd90.min()}).round(3)
    pd.set_option("display.width", 250)
    print(tab.to_string())
    print(res.pivot_table(index="name", columns="era", values="pass60", aggfunc="mean").round(3).to_string())
