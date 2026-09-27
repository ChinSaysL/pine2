"""FTMO challenge odds 2022-07..2026-09: gold EA (v2 settings) alone vs + Nasdaq ORB15 (stop floor 0.3 ATR).
Risk policy v2: cap 1.25%, divisor 4, guards 7% / 3.5%; gold BAD units at 0.5x. 14 workers."""
import itertools, warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from policy_grid import trades as gold_trades, run
from indices import load, daily


def nasdaq(floor_atr=0.3):
    d, cost = load("US100.cash"); D = daily(d)
    out = []
    for day, x in d[(d.hm >= 570) & (d.hm < 960)].groupby("date"):
        if day not in D.index or len(x) < 20 or x.hm.iloc[0] != 570: continue
        o0, c0, hi, lo = x.o.iloc[0], x.c.iloc[0], x.h.iloc[0], x.l.iloc[0]
        a = D.atr[day]
        if c0 == o0 or np.isnan(a): continue
        dr = 1 if c0 > o0 else -1
        rest = x.iloc[1:]; e = rest.o.iloc[0]
        st = lo if dr == 1 else hi
        if (e - st) * dr < floor_atr * a: st = e - dr * floor_atr * a
        risk = (e - st) * dr
        px = xt = None
        for b in rest.itertuples():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px, xt = st, b.utc; break
            if b.hm >= 945: px, xt = b.c, b.utc + pd.Timedelta(minutes=15); break
        if px is None: px, xt = rest.c.iloc[-1], rest.utc.iloc[-1]
        out.append(dict(entry_time=rest.utc.iloc[0], exit_time=xt, r=((px - e) * dr - cost) / risk, stop=px == st))
    return pd.DataFrame(out)


POL = (1.25, 4, 7.0)
PREP = {}
def init():
    g = gold_trades(); n = nasdaq(); n["w"] = 1.0
    g = g[g.entry_time >= "2022-06-01"]
    # gold's regime at each Nasdaq entry = weight of the nearest gold unit is not available -> use the paper file
    pp = pd.read_csv("paper_bm_halfrisk.csv", sep=";")
    pp["x"] = pd.to_datetime(pp.exit_ny, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    pp = pp.dropna(subset=["x"]).sort_values("x")
    ex = pp.x.values.astype("datetime64[ns]"); cum = np.r_[0, np.cumsum(pp.r.values)]
    e = n.entry_time.dt.tz_convert(None).values.astype("datetime64[ns]")
    hi = np.searchsorted(ex, e); lo = np.searchsorted(ex, e - np.timedelta64(60, "D"))
    n["gbad"] = (hi - lo >= 5) & (cum[hi] - cum[lo] < 0)
    PREP["gold"] = F.prepare(g)
    PREP["gold + nasdaq always"] = F.prepare(pd.concat([g, n[["entry_time", "exit_time", "r", "w", "stop"]]]))
    PREP["gold + nasdaq when gold BAD"] = F.prepare(pd.concat([g, n[n.gbad][["entry_time", "exit_time", "r", "w", "stop"]]]))
    PREP["nasdaq alone"] = F.prepare(n[["entry_time", "exit_time", "r", "w", "stop"]])

STARTS = [s for s in pd.date_range("2022-09-01", "2026-06-15", freq="2D", tz=F.PRAGUE) if s.weekday() < 5]
def job(a):
    name, hz, slip = a; t, ev, days = PREP[name]; cap, div, T = POL
    return [(name, hz, slip, s, run(t, ev, days, s, cap, div, T, T / 2, hz, slip)) for s in STARTS
            if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-20", tz="UTC")]

if __name__ == "__main__":
    init()
    with Pool(14, initializer=init) as p:
        res = [r for c in p.imap_unordered(job, list(itertools.product(PREP, (30, 60, 90), (0.0, 0.5)))) for r in c]
    d = pd.DataFrame(res, columns=["name", "hz", "slip", "start", "res"])
    d["era"] = np.where(d.start < pd.Timestamp("2024-01-01", tz="UTC"), "2022-23 (gold ranging)", "2024-26 (gold trending)")
    pd.set_option("display.width", 250)
    s0 = d[d.slip == 0]
    print("PASS"); print(s0.pivot_table(index="name", columns=["era", "hz"], values="res", aggfunc=lambda x: (x == "pass").mean()).round(2).to_string())
    print("\nSTUCK"); print(s0.pivot_table(index="name", columns="hz", values="res", aggfunc=lambda x: (x == "stuck").mean()).round(3).to_string())
    print("\nFTMO BREACH with +0.5R slippage on every stop"); print(d[d.slip == 0.5].pivot_table(index="name", columns="hz", values="res", aggfunc=lambda x: (x == "BREACH").mean()).round(3).to_string())
