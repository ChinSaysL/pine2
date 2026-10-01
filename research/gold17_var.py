"""17-year robustness of the gold strategy's settings + logic variants (BAD regime = half risk).
2010-2019 is out-of-sample for every setting chosen in 2020-26 research."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from pyramid import simulate_pyr
from regime import regime_flag
from oldgold import load_full

BASE = dict(hours=24, n=50, band=1.0, ema=True, trail=3.0, add=(1.0,), stop=2.0)
VARS = {"base": {}, "2nd add +2R": dict(add=(1.0, 2.0)), "no add": dict(add=()), "trail 2.5": dict(trail=2.5), "trail 4": dict(trail=4.0),
        "no EMA200": dict(ema=False), "band 0.5%": dict(band=0.5), "band 1.5%": dict(band=1.5), "SMA 30": dict(n=30), "SMA 100": dict(n=100),
        "channel 12h": dict(hours=12), "channel 48h": dict(hours=48), "stop 1.5": dict(stop=1.5), "stop 2.5": dict(stop=2.5)}
ERAS = [("2010-14", "2010-01-01", "2015-01-01"), ("2015-19", "2015-01-01", "2020-01-01"), ("2020-22", "2020-01-01", "2023-01-01"), ("2023-26", "2023-01-01", "2027-01-01")]
G = {}

def trend(df, n, band, ema):
    closes = df.groupby("tday").c.last()
    sma = closes.rolling(n).mean(); e = closes.ewm(span=200, adjust=False).mean()
    raw = np.where(closes > sma * (1 + band / 100), 1, np.where(closes < sma * (1 - band / 100), -1, 0))
    ok = np.where(raw == 1, closes > e, np.where(raw == -1, closes < e, False)) if ema else raw != 0
    t = pd.Series(np.where(ok & (np.arange(len(closes)) >= 100), raw, 0), index=closes.index).shift(1)
    return df.tday.map(t).fillna(0).values

def trades(name):
    if "g" not in G: G["g"] = load_full("XAUUSD", "data/XAUUSD_H1.csv")
    g = G["g"]; p = dict(BASE, **VARS[name])
    t = simulate_pyr(g, hours=p["hours"], stop_atr=p["stop"], trail_atr=p["trail"], trend=trend(g, p["n"], p["band"], p["ema"]),
                     add_at=p["add"], flat_ny=16 + 50 / 60)
    bad = regime_flag(g, t)
    ei = g.set_index("time").index.get_indexer(pd.DatetimeIndex(t.entry_time))
    t["w"] = np.where(bad[ei], 0.5, 1.0); t["wcap"] = 99
    return t[["entry_time", "exit_time", "r", "w", "wcap"]]

PREP = {}
def init():
    for k in VARS: PREP[k] = F.prepare(trades(k))

def one(a):
    name, hz, s = a
    t, ev, days = PREP[name]
    return name, hz, s, F.run_challenge(t, ev, days, s, F.scaled(1.25, 4, 0.25, int_total=5.0), horizon_days=hz, int_daily=2.5, int_total=5.0)[0]

def era_r(name):
    t = trades(name); t["wr"] = t.r * t.w
    return name, {e: round(t.wr[(t.entry_time >= a) & (t.entry_time < b)].sum(), 1) for e, a, b in ERAS}

if __name__ == "__main__":
    with Pool(14) as p:
        er = dict(p.map(era_r, list(VARS)))
    print("Weighted R by era (BAD trades at 0.5)"); print(pd.DataFrame(er).T.to_string())
    starts = [s for s in pd.date_range("2010-06-01", "2026-06-01", freq="5D", tz=F.PRAGUE) if s.weekday() < 5]
    jobs = [(n, hz, s) for n in VARS for hz in (90, 365) for s in starts if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-20", tz="UTC")]
    with Pool(14, initializer=init) as p:
        res = p.map(one, jobs, chunksize=30)
    d = pd.DataFrame(res, columns=["name", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-26"])
    d["pass"] = d.res == "pass"; d["stuck"] = d.res == "fail"
    pd.set_option("display.width", 300)
    print("\nPASS rate"); print(d.pivot_table(index="name", columns=["hz", "era"], values="pass", aggfunc="mean").round(2).to_string())
    print("\nALL eras"); print(pd.concat([d.pivot_table(index="name", columns="hz", values="pass", aggfunc="mean").add_prefix("pass"),
                                         d.pivot_table(index="name", columns="hz", values="stuck", aggfunc="mean").add_prefix("stuck")], axis=1).round(3).to_string())
    d.to_pickle("gold17_var.pkl")
