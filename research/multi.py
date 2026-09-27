"""Multi-asset trend strategies, judged on the trades they take while GOLD is in its BAD regime.

S1 intraday: the live gold breakout unchanged (24h Donchian, daily SMA50 trend + neutral band + EMA200 side,
   2 ATR stop, 3 ATR trail, add at +1R, flat 16:50 NY). Band = 0.75 daily ATR (gold's 1% ~ 0.7 ATR) so
   it scales to each market's volatility.
S2 swing: 20-day Donchian breakout (turtle style), 2 daily-ATR stop, 3 daily-ATR trail, holds overnight,
   flat Friday 16:50 NY.  No trend filter (the 20-day breakout is the trend signal).
Cost per round trip = 2 x median spread (+ 0.6 bp commission on FX). Results in R per trade.
"""
import sys
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
import pyramid
from concepts import prep
from regime import load_mt5, paper_trades, regime_flag

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
PERIODS = [("dev", "2020-01-01", "2022-07-01"), ("holdA", "2022-07-01", "2024-07-01"), ("holdB", "2024-07-01", "2026-10-01")]
FX_COMM = 0.00006


def load_sym(sym):
    d = pd.read_csv(f"{DATA}\\XX_{sym}_H1.csv").rename(columns={"utc": "time", "open": "o", "high": "h", "low": "l", "close": "c"})
    d["time"] = pd.to_datetime(d.time, utc=True)
    meta = pd.read_csv(f"{DATA}\\XX_meta.csv").set_index("sym").loc[sym]
    fx = len(sym) == 6 and sym[:3] not in ("XPT", "XPD", "XAG")
    px = d.c.median()
    cost = max(2 * meta.spread_med * meta.point, 0.00005 * px) + FX_COMM * px if fx else 2 * meta.spread_med * meta.point
    return prep(d), cost


def trend_atr(df, n=50, band_atr=0.75, ema_len=200):
    d = df.groupby("tday").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    sma = d.c.rolling(n).mean()
    ema = d.c.ewm(span=ema_len, adjust=False).mean()
    raw = np.where(d.c > sma + band_atr * atr, 1, np.where(d.c < sma - band_atr * atr, -1, 0))
    ok = np.where(raw == 1, d.c > ema, np.where(raw == -1, d.c < ema, False))
    t = pd.Series(np.where(ok & (np.arange(len(d)) >= ema_len // 2), raw, 0), index=d.index).shift(1)
    return df.tday.map(t).fillna(0).values


def swing(df, cost, days=20, stop_k=2.0, trail_k=3.0):
    """Daily Donchian breakout on H1 bars: stop orders at the prior `days` high/low, daily ATR stops,
    one position, flat Friday 16:50 NY (weekends are never held)."""
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    d = df.groupby("tday").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
    datr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    hh, ll = d.h.rolling(days).max().shift(1), d.l.rolling(days).min().shift(1)
    tday = df.tday.values
    A, HH, LL = df.tday.map(datr).values, df.tday.map(hh).values, df.tday.map(ll).values
    wd = df.time.dt.tz_convert("America/New_York").dt.weekday.values
    tf = df.tf_h.values[0]
    ny_h = df.ny_h.values
    fri = (wd == 4) & (ny_h + tf > 16 + 50 / 60) & (ny_h < 18) & (ny_h >= 12)
    trades, pos = [], None
    for i in range(1, len(df)):
        a = A[i]
        if np.isnan(a) or np.isnan(HH[i]):
            continue
        if pos is not None:
            dd = pos["dir"]
            if (dd == 1 and l[i] <= pos["stop"]) or (dd == -1 and h[i] >= pos["stop"]):
                px = min(o[i], pos["stop"]) if dd == 1 else max(o[i], pos["stop"])
                trades.append(dict(entry_time=pos["t"], exit_time=df.time.iloc[i], r=((px - pos["e"]) * dd - cost) / pos["risk"]))
                pos = None
            else:
                pos["best"] = max(pos["best"], h[i]) if dd == 1 else min(pos["best"], l[i])
                ns = pos["best"] - dd * trail_k * a
                pos["stop"] = max(pos["stop"], ns) if dd == 1 else min(pos["stop"], ns)
                if fri[i]:
                    trades.append(dict(entry_time=pos["t"], exit_time=df.time.iloc[i], r=((c[i] - pos["e"]) * dd - cost) / pos["risk"]))
                    pos = None
            continue
        if fri[i] or ((ny_h[i] >= 15) & (ny_h[i] < 18) & (wd[i] == 4)):
            continue
        up, dn = h[i] >= HH[i], l[i] <= LL[i]
        if up == dn:
            continue
        dd = 1 if up else -1
        lvl = HH[i] if up else LL[i]
        e = (max(o[i], lvl) if up else min(o[i], lvl)) + dd * 0.05 * df.atr.values[i]
        pos = dict(dir=dd, e=e, stop=e - dd * stop_k * a, risk=stop_k * a, best=e, t=df.time.iloc[i])
    return pd.DataFrame(trades)


def gold_bad_series():
    g = load_mt5("H1")
    return pd.Series(regime_flag(g, paper_trades(g)), index=g.time)


def own_bad(df, trades, days=60, min_trades=5):
    """The instrument's own regime flag from its own paper trades (same rule as gold)."""
    return regime_flag(df, trades, days, min_trades)


def work(sym):
    df, cost = load_sym(sym)
    gb = gold_bad_series()
    pyramid.COST_OZ = cost
    s1 = pyramid.simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=trend_atr(df), add_at=(1.0,), flat_ny=16 + 50 / 60)
    s2 = swing(df, cost)
    out = []
    for name, t in (("S1 intraday", s1), ("S2 swing20", s2)):
        if not len(t):
            continue
        t = t.copy()
        t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values
        ob = own_bad(df, t)
        t["obad"] = ob[df.set_index("time").index.get_indexer(pd.DatetimeIndex(t.entry_time))]
        t["sym"], t["strat"] = sym, name
        out.append(t)
    return out


if __name__ == "__main__":
    syms = pd.read_csv(f"{DATA}\\XX_meta.csv").sym.tolist()
    with Pool(14) as p:
        res = [t for r in p.imap_unordered(work, syms) for t in r]
    allt = pd.concat(res)
    allt.to_pickle("multi_trades.pkl")
    rows = []
    for (sym, strat), t in allt.groupby(["sym", "strat"]):
        row = dict(sym=sym, strat=strat)
        for sel, mask in (("gBAD", t.gbad), ("gBAD+ownGOOD", t.gbad & ~t.obad), ("ALL", t.gbad | ~t.gbad)):
            for p, a, b in PERIODS:
                s = t[mask & (t.entry_time >= a) & (t.entry_time < b)]
                row[f"{sel}|{p}"] = round(s.r.sum(), 1)
        rows.append(row)
    pd.set_option("display.width", 300)
    pd.set_option("display.max_rows", 200)
    print(pd.DataFrame(rows).to_string(index=False))
