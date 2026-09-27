"""Mean-reversion strategies (NOT breakouts), FTMO H1 data, rules fixed before looking at results.

P  Pairs / statistical arbitrage: spread s = log(A) - beta x log(B); beta = OLS of the last 60 daily closes (known
   the day before). z = (s - mean) / sd over the last N hourly bars. |z| > Z -> trade the spread back (sell the rich
   leg, buy beta x the cheap one) from the next bar; exit when z crosses 0, stop when |z| >= 4, max 3 days, flat
   Friday 16:00 NY; entries only in both markets' liquid hours.
   R = (spread P&L - both legs' spreads - financing) / ((4 - Z) x sd at entry).
   FTMO leverage: indices 1:50, FX 1:100 -> both legs together capped at 10x equity at 1.25% risk; trades that
   would need more are sized down (their R scaled).
S  Single-market mean reversion on range-bound crosses (AUDNZD, EURCHF): daily close (16:00 NY) z-score vs the
   20-day mean; |z| > Z -> fade from the next bar, exit at the mean, stop at |z| >= Z + 1.5, max 10 days, flat Friday.
Periods: dev = start..2021-12, hold = 2022-01..2026-09; plus trades while gold is BAD.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
PAIRS = {"GER40/EU50": ("GER40.cash", "EU50.cash", "Europe/Berlin", 540, 1050, 0.0002),
         "US500/US100": ("US500.cash", "US100.cash", "America/New_York", 570, 960, 0.0002),
         "AUDUSD/NZDUSD": ("AUDUSD", "NZDUSD", None, None, None, 0.00005),
         "EURUSD/GBPUSD": ("EURUSD", "GBPUSD", None, None, None, 0.00005)}
MAX_NOTIONAL = 10.0          # both legs, x equity, at 1.25% risk


def load(sym):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_H1.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'H1'").iloc[0]
    rel = (2 * meta.spread_med * meta.point) / d.close.median()
    if len(sym) == 6: rel += 0.00006                      # FX commission
    return d.set_index("utc")[["open", "close"]], rel


def pairs(name, Z=2.0, N=110):
    a_sym, b_sym, tz, h0, h1, fin = PAIRS[name]
    A, ca = load(a_sym); B, cb = load(b_sym)
    df = A.join(B, lsuffix="_a", rsuffix="_b", how="inner").dropna()
    la, lb = np.log(df.close_a), np.log(df.close_b)
    ny = df.index.tz_convert("America/New_York")
    df["tday"] = (ny + pd.Timedelta(hours=7)).date
    daily = pd.DataFrame({"la": la.groupby(df.tday).last(), "lb": lb.groupby(df.tday).last()})
    cov = daily.la.rolling(60).cov(daily.lb); var = daily.lb.rolling(60).var()
    beta = (cov / var).shift(1)
    df["beta"] = df.tday.map(beta)
    s = la - df.beta * lb
    mu, sd = s.rolling(N).mean(), s.rolling(N).std()
    z = ((s - mu) / sd).values
    if tz:
        loc = df.index.tz_convert(tz); hm = loc.hour * 60 + loc.minute
        live = (hm >= h0) & (hm < h1 - 60)
    else:
        nyh = ny.hour; live = ~((nyh >= 16) & (nyh < 20))
    wd, nyh = ny.weekday, ny.hour
    fri = (wd == 4) & (nyh >= 15)
    oa, ob, sv, bv, sdv = df.open_a.values, df.open_b.values, s.values, df.beta.values, sd.values
    out, pos = [], None
    for i in range(N + 1, len(df) - 1):
        if pos is not None:
            held = (df.index[i] - pos["t"]).total_seconds() / 3600
            zi = z[i]
            done = (pos["dir"] * zi >= 0) or abs(zi) >= 4 or held >= 72 or fri[i]
            if done:
                j = i + 1                                   # exit at the next bar's open (both legs)
                s_exit = np.log(oa[j]) - pos["beta"] * np.log(ob[j])
                pnl = pos["dir"] * (s_exit - pos["s"])
                nights = max(0, (df.tday.iloc[j] - pos["day"]).days)
                cost = ca + pos["beta"] * cb + nights * fin * (1 + abs(pos["beta"]))
                out.append(dict(entry_time=pos["t"], exit_time=df.index[j], r=pos["scale"] * (pnl - cost) / pos["risk"],
                                lev=pos["lev"], scale=pos["scale"]))
                pos = None
            continue
        if not live[i] or fri[i] or np.isnan(z[i]) or np.isnan(bv[i]) or abs(z[i]) <= Z or bv[i] <= 0: continue
        j = i + 1
        risk = (4 - Z) * sdv[i]
        lev = 0.0125 / risk * (1 + bv[i])                    # both legs' notional, x equity, at 1.25% risk
        scale = min(1.0, MAX_NOTIONAL / lev)
        pos = dict(dir=-int(np.sign(z[i])), s=np.log(oa[j]) - bv[i] * np.log(ob[j]), beta=bv[i], risk=risk, t=df.index[j],
                   day=df.tday.iloc[j], lev=lev, scale=scale)
    return pd.DataFrame(out)


def single(sym, Z=2.0):
    A, ca = load(sym)
    ny = A.index.tz_convert("America/New_York")
    A["tday"] = (ny + pd.Timedelta(hours=7)).date
    dc = A.close.groupby(A.tday).last()
    mu, sd = dc.rolling(20).mean().shift(1), dc.rolling(20).std().shift(1)
    A["mu"], A["sd"] = A.tday.map(mu), A.tday.map(sd)
    at16 = ny.hour == 16
    fri = (ny.weekday == 4) & (ny.hour >= 15)
    o, c = A.open.values, A.close.values
    out, pos = [], None
    for i in range(1, len(A) - 1):
        m, s_ = A.mu.iat[i], A.sd.iat[i]
        if np.isnan(m) or s_ <= 0: continue
        zi = (c[i] - m) / s_
        if pos is not None:
            done = (pos["dir"] * (c[i] - m) >= 0) or abs(zi) >= Z + 1.5 or (A.index[i] - pos["t"]).days >= 10 or fri[i]
            if done:
                px = o[i + 1]; pnl = pos["dir"] * (px - pos["e"]) / pos["e"]
                out.append(dict(entry_time=pos["t"], exit_time=A.index[i + 1], r=(pnl - ca - 0.00005 * (A.index[i + 1] - pos["t"]).days) / pos["risk"]))
                pos = None
            continue
        if at16[i] and not fri[i] and abs(zi) > Z:
            e = o[i + 1]; pos = dict(dir=-int(np.sign(zi)), e=e, risk=1.5 * s_ / e, t=A.index[i + 1])
    return pd.DataFrame(out)


JOBS = [("P", n, dict(Z=z, N=N)) for n in PAIRS for z in (2.0, 2.5) for N in (110, 220)]
JOBS += [("S", s, dict(Z=z)) for s in ("AUDNZD", "EURCHF") for z in (2.0, 2.5)]


def job(j):
    k, n, kw = j
    t = pairs(n, **kw) if k == "P" else single(n, **kw)
    t["name"] = f"{'pair' if k == 'P' else 'MR'} {n} {kw}"
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, JOBS)
    from indices import gold_bad
    gb = gold_bad()
    rows = []; allt = []
    for t in res:
        if not len(t): continue
        t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values.astype(bool)
        allt.append(t)
        row = {"name": t.name.iloc[0]}
        for p, a, b in [("dev ..2021", "2000-01-01", "2022-01-01"), ("hold 2022-26", "2022-01-01", "2027-01-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p] = f"{x.r.sum():+6.1f}R n={len(x):4d} PF={pf:4.2f} win={100 * (x.r > 0).mean():3.0f}%"
        row["gold BAD"] = round(t.r[t.gbad].sum(), 1)
        if "lev" in t: row["legs x equity med/p95"] = f"{t.lev.median():.1f}/{t.lev.quantile(.95):.1f}"; row["sized down"] = f"{(t.scale < 1).mean():.0%}"
        rows.append(row)
    pd.concat(allt).to_pickle("pairs_trades.pkl")
    pd.set_option("display.width", 260)
    print(pd.DataFrame(rows).fillna("").to_string(index=False))
