"""Third-strategy search, round 2 - intraday only, flat before the close, never holding through a release.

A  FX post-release momentum (FTMO M15, 2015-2026): the 08:30-08:45 NY candle's range >= k x its median over the
   previous 20 days (= a US data release moved the market); enter at 08:45 in its direction (after the release),
   stop at its opposite extreme (floor 0.3 daily ATR), exit 11:00 or 15:55 NY. Control: opposite direction.
B  Stock earnings-day intraday (FTMO US stock CFDs, daily bars): gap >= k x ATR% at the open.
   B0 gap day: open -> close in the gap direction, stop 1 ATR (stop assumed hit first if touched - conservative).
   B1 day after a confirmed event (gap, 2x volume, close in gap direction): open -> close, stop 1 ATR.
Costs: FX 2 x median spread + 0.6 bp; stocks 2 x median spread + 0.02% slippage per side. R per trade.
dev = up to 2021, hold = 2022-2026."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import fx

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"


def fx_release(sym, k=2.0, exit_hm=660, side=1):
    d, cost = fx.load(sym, "M15")
    x = d[(d.ny_hm >= 510) & (d.ny_hm < 960)]
    days = {day: g.reset_index(drop=True) for day, g in x.groupby("ny_date")}
    rng = {day: (g.h.iat[0] - g.l.iat[0]) for day, g in days.items() if g.ny_hm.iat[0] == 510}
    rs = pd.Series(rng); med = rs.rolling(20).median().shift(1)
    out = []
    for day, g in days.items():
        if day not in rs.index or g.ny_hm.iat[0] != 510 or len(g) < 4: continue
        m = med.get(day, np.nan); a = g.datr.iat[0]
        if np.isnan(m) or np.isnan(a) or rs[day] < k * m: continue
        b0 = g.iloc[0]
        if b0.c == b0.o: continue
        dr = (1 if b0.c > b0.o else -1) * side
        rest = g.iloc[1:]; e = rest.o.iat[0]
        st = (b0.l if dr == 1 else b0.h) if side == 1 else (b0.h + 0.1 * a if dr == -1 else b0.l - 0.1 * a)
        if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
        risk = (e - st) * dr; px = xt = None
        for b in rest.itertuples():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px, xt = st, b.utc; break
            if b.ny_hm >= exit_hm: px, xt = b.o, b.utc; break
        if px is None: px, xt = rest.c.iat[-1], rest.utc.iat[-1]
        out.append(dict(entry_time=rest.utc.iat[0], exit_time=xt, r=((px - e) * dr - cost) / risk))
    return pd.DataFrame(out)


def stock_intraday(sym, k=2.0, mode="B0", side=1):
    meta = pd.read_csv(f"{DATA}\\STK_meta.csv").set_index("sym")
    d = pd.read_csv(f"{DATA}\\STK_{sym}_D1.csv", parse_dates=["date"])
    o, h, l, c, v = d.open.values, d.high.values, d.low.values, d.close.values, d.tick_volume.values.astype(float)
    tr = np.maximum(d.high - d.low, np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().values
    vavg = pd.Series(v).rolling(20).mean().shift(1).values
    sp = 2 * meta.loc[sym, "spread_med"] * meta.loc[sym, "point"]
    out = []
    for t in range(21, len(d) - 2):
        gap = o[t] / c[t - 1] - 1; atrp = atr[t - 1] / c[t - 1]
        if abs(gap) < k * atrp: continue
        if mode == "B0":
            i = t; dr = int(np.sign(gap)) * side; dist = atr[t - 1]
        else:
            if not (v[t] >= 2 * vavg[t] and np.sign(c[t] - o[t]) == np.sign(gap)): continue
            i = t + 1; dr = int(np.sign(gap)) * side; dist = atr[t]
        e = o[i]; st = e - dr * dist
        hit = (l[i] <= st) if dr == 1 else (h[i] >= st)
        px = st if hit else c[i]
        out.append(dict(entry_time=d.date.iat[i], exit_time=d.date.iat[i], sym=sym, r=((px - e) * dr - sp - 0.0004 * e) / dist))
    return pd.DataFrame(out)


FXS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
STK = list(pd.read_csv(f"{DATA}\\STK_meta.csv").sym)
JOBS = [("A", s, dict(k=k, exit_hm=x)) for s in FXS for k in (2.0, 3.0) for x in (660, 955)]
JOBS += [("A", s, dict(k=2.0, exit_hm=955, side=-1)) for s in FXS]
JOBS += [("B", m, dict(k=k, mode=m)) for m in ("B0", "B1") for k in (2.0, 3.0)]
JOBS += [("B", m, dict(k=2.0, mode=m, side=-1)) for m in ("B0", "B1")]


def job(j):
    kind, s, kw = j
    if kind == "A":
        t = fx_release(s, **kw)
        t["name"] = f"A post-release {s} k{kw['k']} exit {'11:00' if kw['exit_hm'] == 660 else '15:55'}{' CONTROL(opposite)' if kw.get('side') == -1 else ''}"
    else:
        t = pd.concat([stock_intraday(x, **kw) for x in STK])
        t["entry_time"] = pd.to_datetime(t.entry_time).dt.tz_localize("America/New_York").dt.tz_convert("UTC") + pd.Timedelta(hours=9, minutes=30)
        t["name"] = f"B stocks {'gap day' if kw['mode'] == 'B0' else 'day after event'} k{kw['k']}{' CONTROL(opposite)' if kw.get('side') == -1 else ''}"
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, JOBS)
    from indices import gold_bad
    gb = gold_bad(); rows = []; allt = []
    for t in res:
        if not len(t): continue
        t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values.astype(bool)
        allt.append(t); row = {"name": t.name.iloc[0]}
        for p_, a, b in [("dev ..2021", "2000-01-01", "2022-01-01"), ("hold 2022-26", "2022-01-01", "2027-01-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p_] = f"{x.r.sum():+7.1f}R n={len(x):4d} PF={pf:4.2f} avg={x.r.mean():+.3f}"
        yr = t.groupby(t.entry_time.dt.year).r.sum(); row["yrs+"] = f"{(yr > 0).sum()}/{len(yr)}"
        rows.append(row)
    pd.concat(allt).to_pickle("third2_trades.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(pd.DataFrame(rows).to_string(index=False))
