"""Long-history (2010/2012 - 2026) test of pre-registered strategy families on FTMO-tradable markets.
F1 intraday breakout (gold rules, band 0.75 daily ATR, own regime -> half risk)
F2 20-day swing breakout, daily-ATR stops/trail, flat Friday
F3 indices: daily RSI(2) < 10 pullback while above the 200-day SMA, long only, exit close > 5-day SMA or 10 days,
   3 daily-ATR catastrophe stop, flat Friday, financing 0.02% of price per night
F4 indices: overnight drift - buy the 16:00 NY cash close, sell 09:00 NY, Mon-Thu, 1 daily-ATR stop, financing
Costs: 2 x the larger of the old/new median spread (+0.6 bp commission on FX). Results in R; eras 2012-15, 2016-19,
2020-22, 2023-26; 'gBAD' = trades taken while the gold strategy is in its BAD regime."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import gen as G, pyramid
from concepts import prep
from multi import trend_atr, swing
from regime import regime_flag, paper_trades
from oldgold import load_full as load_gold

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
INDICES = ["US500", "US30", "DE40"]
MARKETS = INDICES + ["XAGUSD", "XPTUSD", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDJPY", "USDCHF", "EURJPY", "GBPJPY", "AUDJPY"]
ERAS = [("2012-15", "2012-01-01", "2016-01-01"), ("2016-19", "2016-01-01", "2020-01-01"), ("2020-22", "2020-01-01", "2023-01-01"), ("2023-26", "2023-01-01", "2027-01-01")]
FIN = 0.0002


def load(sym):
    a = pd.read_csv(f"{DATA}\\OLD_{sym}_H1.csv"); b = pd.read_csv(f"{DATA}\\XX_{sym}_H1.csv")
    meta = pd.read_csv(f"{DATA}\\XX_meta.csv").set_index("sym").loc[sym]
    spread = max(a.spread.median(), b.spread.median()) * meta.point
    d = pd.concat([a, b]).drop_duplicates("utc").sort_values("utc").rename(columns={"utc": "time", "open": "o", "high": "h", "low": "l", "close": "c"})
    d["time"] = pd.to_datetime(d.time, utc=True)
    df = prep(d.reset_index(drop=True))
    fx = len(sym) == 6 and sym[:3] not in ("XAG", "XPT")
    px = df.c.median()
    cost = 2 * spread + (0.00006 * px if fx else 0)
    return df, cost


def f3_rsi2(df, cost):
    D = G.daily_frame(df)
    delta = D.c.diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(); dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    D["rsi"] = 100 - 100 / (1 + up / dn); D["sma5"] = D.c.rolling(5).mean(); D["sma200"] = D.c.rolling(200).mean()
    P = D.shift(1)
    tday, c = df.tday.values, df.c.values
    end_h = (df.ny_h.values + df.tf_h.values[0]) % 24

    def g(i):
        if abs(end_h[i] - 20.0) > 1e-6: return None
        td = tday[i]
        if td not in P.index: return None
        p = P.loc[td]
        if np.isnan(p.sma200) or not (p.c > p.sma200 and p.rsi < 10): return None
        return [dict(dir=1, stop_dist=3 * p.atr, swing=True,
                     exit_fn=lambda j, q: abs(end_h[j] - 16.0) < 1e-6 and (c[j] > P.sma5.get(tday[j], np.inf) or j - q["i"] > 10 * 23 / df.tf_h.values[0]))]
    t = G.run(df, g, cost=cost, swing_entries=True)
    return t


def f4_overnight(df, cost):
    D = G.daily_frame(df); P = D.shift(1)
    tday = df.tday.values
    end_h = (df.ny_h.values + df.tf_h.values[0]) % 24
    wd = df.time.dt.tz_convert("America/New_York").dt.weekday.values

    def g(i):
        if abs(end_h[i] - 16.0) > 1e-6 or wd[i] == 4: return None
        a = P.atr.get(tday[i], np.nan)
        return None if np.isnan(a) else [dict(dir=1, stop_dist=a, exit_at=9.0, swing=True)]
    return G.run(df, g, cost=cost, swing_entries=True)


def financing(t, df):
    if not len(t): return t
    nights = (pd.to_datetime(t.exit_time).dt.tz_convert("America/New_York") + pd.Timedelta(hours=7)).dt.normalize() - \
             (pd.to_datetime(t.entry_time).dt.tz_convert("America/New_York") + pd.Timedelta(hours=7)).dt.normalize()
    n = nights.dt.days.clip(lower=0)
    t = t.copy(); t["r"] = t.r - n * FIN * t.entry / t.risk
    return t


def gold_bad():
    g = load_gold("XAUUSD", f"{DATA}\\XAUUSD_H1.csv")
    return pd.Series(regime_flag(g, paper_trades(g)), index=g.time)


def work(sym):
    df, cost = load(sym)
    gb = gold_bad()
    out = {}
    pyramid.COST_OZ = cost
    t1 = pyramid.simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=trend_atr(df), add_at=(1.0,), flat_ny=16 + 50 / 60)
    ob = regime_flag(df, t1)
    ei = df.set_index("time").index.get_indexer(pd.DatetimeIndex(t1.entry_time))
    t1["r"] = t1.r * np.where(ob[ei], 0.5, 1.0)
    out["F1 intraday BO"] = t1
    out["F2 swing20"] = swing(df, cost)
    if sym in INDICES:
        out["F3 RSI2 dip"] = financing(f3_rsi2(df, cost), df)
        out["F4 overnight"] = financing(f4_overnight(df, cost), df)
    rows = []
    for fam, t in out.items():
        if not len(t): continue
        t = t.copy(); t["entry_time"] = pd.to_datetime(t.entry_time, utc=True)
        t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values.astype(bool)
        row = dict(sym=sym, family=fam)
        for e, a, b in ERAS:
            s = t[(t.entry_time >= a) & (t.entry_time < b)]
            row[e] = round(s.r.sum(), 1)
            row[e + " gBAD"] = round(s.r[s.gbad].sum(), 1)
        row["n/yr"] = round(len(t[t.entry_time >= "2012-01-01"]) / 14.7, 0)
        rows.append(row)
        t[["entry_time", "exit_time", "r", "gbad"]].assign(sym=sym, family=fam).to_pickle(f"ml_{sym}_{fam.split()[0]}.pkl")
    return rows


if __name__ == "__main__":
    with Pool(14) as p:
        rows = [r for res in p.imap_unordered(work, MARKETS) for r in res]
    d = pd.DataFrame(rows).sort_values(["family", "sym"])
    d.to_csv("markets_long.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200)
    print(d.to_string(index=False))
