"""Wide concept search for the BAD regime. Every concept x neighbour grid, fixed before looking at results.

Pass rule (fixed in advance): BAD-regime R > 0 with PF >= 1.1 in BOTH dev (2020-01..2022-06) and holdA
(2022-07..2024-06); >= 2/3 of the concept's neighbours positive in both; holdB (2024-07..2026-09) BAD
not worse than -5R.  Survivors are then re-checked on M15 and with double costs.
"""
import itertools
import sys
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
import gen as G
from regime import load_mt5, paper_trades, regime_flag, trend_array
from pyramid import simulate_pyr

PERIODS = [("dev", "2020-01-01", "2022-07-01"), ("holdA", "2022-07-01", "2024-07-01"), ("holdB", "2024-07-01", "2026-10-01")]
DATA = {}


def setup():
    h1 = load_mt5("H1")
    bad_h1 = regime_flag(h1, paper_trades(h1))
    m30 = load_mt5("M30")
    bad_m30 = pd.Series(bad_h1, index=h1.time).reindex(m30.time.dt.floor("h")).fillna(False).values
    eu = pd.read_csv(r"c:\Users\Abdo\Downloads\pine2\research\data\EURUSD_H1.csv")
    eu["time"] = pd.to_datetime(eu.utc, utc=True)
    h1["eu"] = h1.time.map(eu.set_index("time").close).ffill().values
    DATA.update(H1=(h1, bad_h1, G.daily_frame(h1)), M30=(m30, bad_m30, G.daily_frame(m30)))


def ctx(tf):
    df, bad, D = DATA[tf]
    P = D.shift(1)                      # previous trading day, known at the start of each day
    first = np.r_[True, df.tday.values[1:] != df.tday.values[:-1]]
    end_h = (df.ny_h.values + df.tf_h.values[0]) % 24
    return df, bad, D, P, first, end_h


# ---------------------------------------------------------------------------------------------- concepts
def A_compression(tf, kind, stop_mode, tgt):
    """Previous day was NR4 / NR7 / inside day -> OCO stop orders at its high/low all next day."""
    df, bad, D, P, first, end_h = ctx(tf)
    nr = {"NR4": D.rng <= D.rng.rolling(4).min(), "NR7": D.rng <= D.rng.rolling(7).min(),
          "inside": (D.h <= D.h.shift()) & (D.l >= D.l.shift())}[kind].shift(1).fillna(False)
    tday = df.tday.values
    k = int(20 / df.tf_h.values[0])

    def g(i):
        if not first[i]:
            return None
        td = tday[i]
        if not nr.get(td, False) or np.isnan(P.atr.get(td, np.nan)):
            return None
        ph, pl, a = P.h[td], P.l[td], P.atr[td]
        buf = 0.02 * a
        sl_l = pl if stop_mode == "opp" else (ph + pl) / 2
        sl_s = ph if stop_mode == "opp" else (ph + pl) / 2
        return [dict(kind="stop", dir=1, trigger=ph + buf, stop=sl_l, tgt_r=tgt, valid=k),
                dict(kind="stop", dir=-1, trigger=pl - buf, stop=sl_s, tgt_r=tgt, valid=k)]
    return g, dict(last_entry_ny=15.0)


def B_intraday_mom(tf, T, kmin, stop_k, sign):
    """At NY hour T: day's move since the 18:00 open > kmin x daily ATR -> trade with it (sign=+1) or fade (-1)."""
    df, bad, D, P, first, end_h = ctx(tf)
    tday, c = df.tday.values, df.c.values

    def g(i):
        if abs(end_h[i] - T) > 1e-6:
            return None
        td = tday[i]
        a = P.atr.get(td, np.nan)
        if np.isnan(a):
            return None
        mv = c[i] - D.o[td]
        if abs(mv) < kmin * a or mv == 0:
            return None
        d = int(np.sign(mv)) * sign
        return [dict(dir=d, stop_dist=stop_k * a)]
    return g, {}


def C_overnight(tf, entry, exit_, d):
    """Fixed session drift: enter at NY hour `entry`, exit at NY hour `exit_`, stop 1 daily ATR."""
    df, bad, D, P, first, end_h = ctx(tf)
    tday = df.tday.values

    def g(i):
        if abs(end_h[i] - entry) > 1e-6:
            return None
        a = P.atr.get(tday[i], np.nan)
        return None if np.isnan(a) else [dict(dir=d, stop_dist=a, exit_at=exit_)]
    return g, {}


def D_burst(tf, bars, m, hold, tgt):
    """Momentum burst: move over the last `bars` bars > m ATR -> go with it for `hold` bars."""
    df, bad, D, P, first, end_h = ctx(tf)
    c, atr = df.c.values, df.atr.values

    def g(i):
        if i < bars or np.isnan(atr[i]):
            return None
        mv = c[i] - c[i - bars]
        if abs(mv) < m * atr[i]:
            return None
        return [dict(dir=int(np.sign(mv)), stop_dist=1.5 * atr[i], hold=hold, tgt_r=tgt)]
    return g, {}


def E_stretch_mom(tf, k, exit_mode):
    """Close > k ATR above the 24h average -> ride it (the mirror of the losing fade)."""
    df, bad, D, P, first, end_h = ctx(tf)
    c, atr = df.c.values, df.atr.values
    nb = int(24 / df.tf_h.values[0])
    ma = pd.Series(c).rolling(nb).mean().values

    def g(i):
        if np.isnan(ma[i]) or np.isnan(atr[i]):
            return None
        d = 1 if c[i] > ma[i] + k * atr[i] else (-1 if c[i] < ma[i] - k * atr[i] else 0)
        if not d:
            return None
        od = dict(dir=d, stop_dist=1.5 * atr[i])
        if exit_mode == "ma":
            od["exit_fn"] = lambda j, p: (c[j] - ma[j]) * p["dir"] < 0
        else:
            od["tgt_r"] = 2.0
        return [od]
    return g, {}


def I_dollar_lead(tf, L, z, lag):
    """EURUSD moved strongly over L hours (dollar weak/strong) -> trade gold the same way for 4 hours.
    lag=True: only if gold has not followed yet (gold's L-hour move < 0.5 of its own sd)."""
    df, bad, D, P, first, end_h = ctx(tf)
    eu, c, atr = df.eu.values, df.c.values, df.atr.values
    re = pd.Series(np.log(eu)).diff(L)
    ze = (re / re.rolling(500).std()).values
    rg = pd.Series(np.log(c)).diff(L)
    zg = (rg / rg.rolling(500).std()).values

    def g(i):
        if np.isnan(ze[i]) or abs(ze[i]) < z:
            return None
        d = int(np.sign(ze[i]))
        if lag and zg[i] * d > 0.5:
            return None
        return [dict(dir=d, stop_dist=1.5 * atr[i], hold=4)]
    return g, {}


def J_daily_swing(tf, look, pct):
    """Close in the bottom/top pct of the `look`-day range AND the day reversed -> swing to the 10d SMA."""
    df, bad, D, P, first, end_h = ctx(tf)
    lo, hi = D.l.rolling(look).min(), D.h.rolling(look).max()
    posn = ((D.c - lo) / (hi - lo)).shift(1)
    up = (D.c > D.o).shift(1).fillna(False)
    sma = D.c.rolling(10).mean().shift(1)
    tday, c = df.tday.values, df.c.values
    start = {}

    def g(i):
        if abs(end_h[i] - 20.0) > 1e-6:
            return None
        td = tday[i]
        p, a = posn.get(td, np.nan), P.atr.get(td, np.nan)
        if np.isnan(p) or np.isnan(a):
            return None
        d = 1 if (p <= pct and up[td]) else (-1 if (p >= 1 - pct and not up[td]) else 0)
        if not d:
            return None
        s = sma[td]
        return [dict(dir=d, stop_dist=1.5 * a, swing=True,
                     exit_fn=lambda j, q: abs(end_h[j] - 16.5) < 1e-6 and ((c[j] - s) * q["dir"] > 0 or j - q["i"] > 5 * 23 / df.tf_h.values[0]))]
    return g, {}


def K_followthrough(tf, m, cp):
    """Yesterday was a big range day (> m x ATR) closing in its top/bottom cp -> continue today."""
    df, bad, D, P, first, end_h = ctx(tf)
    big = (D.rng > m * D.atr.shift()).shift(1).fillna(False)
    loc = ((D.c - D.l) / D.rng).shift(1)
    tday = df.tday.values

    def g(i):
        if abs(end_h[i] - 20.0) > 1e-6:
            return None
        td = tday[i]
        if not big.get(td, False):
            return None
        d = 1 if loc[td] >= 1 - cp else (-1 if loc[td] <= cp else 0)
        return [dict(dir=d, stop_dist=P.atr[td])] if d else None
    return g, {}


def L_comex_fade(tf, k, retr):
    """At 13:30 NY (COMEX close) fade a day move > k x ATR, target `retr` of it back, stop 0.5 ATR beyond."""
    df, bad, D, P, first, end_h = ctx(tf)
    tday, c = df.tday.values, df.c.values

    def g(i):
        if abs(end_h[i] - 13.5) > 1e-6:
            return None
        td = tday[i]
        a = P.atr.get(td, np.nan)
        mv = c[i] - D.o[td]
        if np.isnan(a) or abs(mv) < k * a:
            return None
        d = -int(np.sign(mv))
        return [dict(dir=d, stop_dist=0.5 * a, target=c[i] + d * retr * abs(mv))]
    return g, {}


def M_weekly(tf, stop_mode, tgt):
    """Monday's range; Tue-Thu OCO stop orders at its high/low; hold to Friday 16:50."""
    df, bad, D, P, first, end_h = ctx(tf)
    tday = df.tday.values
    k = int(3 * 23 / df.tf_h.values[0])

    def g(i):
        if not first[i]:
            return None
        td = tday[i]
        if D.wd.get(td) != 1 or P.wd.get(td) != 0:
            return None
        ph, pl = P.h[td], P.l[td]
        a = P.atr[td]
        sl_l = pl if stop_mode == "opp" else (ph + pl) / 2
        sl_s = ph if stop_mode == "opp" else (ph + pl) / 2
        return [dict(kind="stop", dir=1, trigger=ph + 0.02 * a, stop=sl_l, tgt_r=tgt, valid=k, swing=True),
                dict(kind="stop", dir=-1, trigger=pl - 0.02 * a, stop=sl_s, tgt_r=tgt, valid=k, swing=True)]
    return g, {}


def P_quick_bo(tf, tgt, trend):
    """24h Donchian breakout, stop 2 ATR, fixed target (take profits fast in noisy markets)."""
    df, bad, D, P, first, end_h = ctx(tf)
    h, l, atr = df.h.values, df.l.values, df.atr.values
    nb = int(24 / df.tf_h.values[0])
    hh = pd.Series(h).rolling(nb).max().values
    ll = pd.Series(l).rolling(nb).min().values
    tr = trend_array(df) if trend else np.zeros(len(df))

    def g(i):
        if np.isnan(hh[i]) or np.isnan(atr[i]):
            return None
        a = atr[i]
        out = []
        if not trend or tr[i] == 1:
            t = hh[i] + 0.05 * a
            out.append(dict(kind="stop", dir=1, trigger=t, stop=t - 2 * a, tgt_r=tgt))
        if not trend or tr[i] == -1:
            t = ll[i] - 0.05 * a
            out.append(dict(kind="stop", dir=-1, trigger=t, stop=t + 2 * a, tgt_r=tgt))
        return out
    return g, {}


def F_fast_trend(tf, n, band):
    """The live breakout (trail + add) but with a faster daily trend filter (n-day SMA)."""
    return ("pyr", n, band)


JOBS = []
JOBS += [("A_compression", "M30", a) for a in itertools.product(["NR4", "NR7", "inside"], ["opp", "mid"], [2.0, None])]
JOBS += [("B_intraday_mom", "M30", a) for a in itertools.product([9.0, 11.0, 13.0], [0.25, 0.5], [0.5, 0.75], [1])]
JOBS += [("B_intraday_mom", "M30", a) for a in itertools.product([11.0, 13.0], [0.5, 1.0], [0.5], [-1])]
JOBS += [("C_overnight", "M30", a) for a in [(19.0, 3.0, 1), (19.0, 7.0, 1), (20.0, 3.0, 1), (20.0, 7.0, 1),
                                             (8.0, 16.5, -1), (10.0, 16.5, -1), (3.0, 8.0, 1), (3.0, 8.0, -1)]]
JOBS += [("D_burst", "M30", a) for a in itertools.product([2, 4], [2.0, 3.0], [4, 8], [None])]
JOBS += [("E_stretch_mom", "H1", a) for a in itertools.product([1.5, 2.0, 2.5], ["ma", "2r"])]
JOBS += [("F_fast_trend", "H1", a) for a in itertools.product([5, 10, 20], [0.0, 1.0])]
JOBS += [("I_dollar_lead", "H1", a) for a in itertools.product([1, 2, 4], [1.5, 2.0], [False, True])]
JOBS += [("J_daily_swing", "M30", a) for a in itertools.product([10, 20], [0.1, 0.2])]
JOBS += [("K_followthrough", "M30", a) for a in itertools.product([1.3, 1.6], [0.2, 0.3])]
JOBS += [("L_comex_fade", "M30", a) for a in itertools.product([0.5, 1.0], [0.5, 1.0])]
JOBS += [("M_weekly", "M30", a) for a in itertools.product(["opp", "mid"], [2.0, None])]
JOBS += [("P_quick_bo", "H1", a) for a in itertools.product([1.0, 1.5, 2.0], [True, False])]


def trend_n(df, n, band):
    closes = df.groupby("tday").c.last()
    sma = closes.rolling(n).mean()
    raw = pd.Series(np.where(closes > sma * (1 + band / 100), 1, np.where(closes < sma * (1 - band / 100), -1, 0)),
                    index=closes.index).shift(1)
    return df.tday.map(raw).fillna(0).values


def work(job):
    name, tf, args = job
    if not DATA:
        setup()
    df, bad, D = DATA[tf]
    out = []
    if name == "F_fast_trend":
        n, band = args
        t = simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=trend_n(df, n, band), add_at=(1.0,),
                         flat_ny=16 + 50 / 60)
        ei = df.set_index("time").index.get_indexer(pd.DatetimeIndex(t.entry_time))
        res = {"BAD": t[bad[ei]], "ALL": t}
    else:
        fn = globals()[name]
        res = {}
        for mode, al in (("BAD", bad), ("ALL", None)):
            g, kw = fn(tf, *args)
            res[mode] = G.run(df, g, allowed=al, **kw)
    for mode, t in res.items():
        row = dict(concept=name, args=str(args), mode=mode)
        for p, a, b in PERIODS:
            s = t[(t.entry_time >= a) & (t.entry_time < b)] if len(t) else t
            r = s.r if len(s) else pd.Series(dtype=float)
            row[p + "_R"] = round(r.sum(), 1)
            row[p + "_n"] = len(r)
            row[p + "_PF"] = round(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), 2)
        out.append(row)
    return out


if __name__ == "__main__":
    with Pool(14) as pool:
        rows = [r for res in pool.imap_unordered(work, JOBS) for r in res]
    df = pd.DataFrame(rows).sort_values(["concept", "args", "mode"])
    df.to_csv("brainstorm_results.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    print(df[df["mode"] == "BAD"].to_string(index=False))
