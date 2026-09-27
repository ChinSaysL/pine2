"""Robustness of the US100 opening-range momentum (ORB15, hold to 15:55 NY) on FTMO M15 data."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
from indices import load, daily, strat_A, gold_bad


def orb(d, D, cost, minutes=15, exit_hm=945, stop_frac=1.0, skip_small=0.0):
    """stop_frac: stop at this fraction of the opening range from the entry side (1.0 = opposite extreme).
    skip_small: skip days whose opening range < skip_small x daily ATR."""
    out = []
    by = dict(tuple(d[(d.hm >= 570) & (d.hm < 960)].groupby("date")))
    k = minutes // 15
    for day, x in by.items():
        if day not in D.index or len(x) < 20 or x.hm.iloc[0] != 570: continue
        first = x.iloc[:k]
        o0, c0, hi, lo = first.o.iloc[0], first.c.iloc[-1], first.h.max(), first.l.min()
        a = D.atr[day]
        if c0 == o0 or np.isnan(a) or (hi - lo) < skip_small * a: continue
        dr = 1 if c0 > o0 else -1
        rest = x.iloc[k:]
        e = rest.o.iloc[0]
        st = e - dr * stop_frac * (hi - lo) if stop_frac != 1.0 else (lo if dr == 1 else hi)
        risk = (e - st) * dr
        if risk <= 0: continue
        px, xt = None, None
        for _, b in rest.iterrows():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px, xt = st, b.utc; break
            if b.hm >= exit_hm: px, xt = b.c, b.utc; break
        if px is None: px, xt = rest.c.iloc[-1], rest.utc.iloc[-1]
        out.append(dict(entry_time=rest.utc.iloc[0], exit_time=xt + pd.Timedelta(minutes=15), r=((px - e) * dr - cost) / risk,
                        risk_pct=100 * risk / e))
    return pd.DataFrame(out)


VARS = {"base ORB15 EOD": {}, "cost x2 (4x spread)": {"cost_mult": 2}, "cost x3": {"cost_mult": 3},
        "exit 15:30": {"exit_hm": 915}, "exit 14:00": {"exit_hm": 825}, "stop 0.5 range": {"stop_frac": 0.5},
        "skip tiny range (<0.1 ATR)": {"skip_small": 0.1}, "ORB30": {"minutes": 30}, "ORB45": {"minutes": 45}}


def job(name):
    d, cost = load("US100.cash"); D = daily(d)
    kw = dict(VARS[name]); cm = kw.pop("cost_mult", 1)
    t = orb(d, D, cost * cm, **kw); t["name"] = name
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, list(VARS))
    t = pd.concat(res)
    t["half"] = t.entry_time.dt.year.astype(str) + np.where(t.entry_time.dt.month <= 6, "H1", "H2")
    t.to_pickle("nasdaq_orb.pkl")
    pd.set_option("display.width", 250)
    print("R by half-year"); print(t.pivot_table(index="name", columns="half", values="r", aggfunc="sum").round(1).to_string())
    s = t[t.name == "base ORB15 EOD"]
    print("\nbase: n", len(s), "win%", round((s.r > 0).mean() * 100, 1), "avg R", round(s.r.mean(), 3), "median risk % of price",
          round(s.risk_pct.median(), 3), "worst R", round(s.r.min(), 2), "best R", round(s.r.max(), 2))
    print("max losing streak:", max(len(list(g)) for k, g in __import__("itertools").groupby(s.r < 0) if k))
    gb = gold_bad(); s["gbad"] = gb.reindex(pd.DatetimeIndex(s.entry_time).floor("h")).fillna(False).values.astype(bool)
    print("gold BAD: n", s.gbad.sum(), "R", round(s.r[s.gbad].sum(), 1), "| gold GOOD: n", (~s.gbad).sum(), "R", round(s.r[~s.gbad].sum(), 1))
