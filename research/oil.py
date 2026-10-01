"""Crude oil strategies designed from oil's own behaviour (FTMO USOIL.cash / UKOIL.cash).

E  EIA weekly inventory report (Wednesday 10:30 NY). Reaction bar 10:30-10:45 (or 10:30-11:00).
   Emom: trade in the reaction's direction from the next bar; Efade: trade against it.
   Stop at the reaction range's opposite side (momentum) / beyond its extreme (fade), floor 0.3 daily ATR;
   exit 14:15 NY (before the 14:30 NYMEX settlement) or 12:00.
N  NYMEX open (09:00 NY): first 15-min candle's direction, stop at its opposite extreme (floor 0.3 ATR), exit 14:15.
T  Multi-week trend (oil = the classic trend market): 20-day / 55-day breakout on daily closes, stop 2 daily ATR,
   trail 3 daily ATR, held overnight, flat Friday before the weekend; financing 0.02% per night. H1 data (UKOIL 2016+).
Costs 2 x median FTMO spread (x3 stress for the EIA trades, spreads widen at the release). R per trade.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
from indices import load, gold_bad

PERIODS = [("dev", "2022-01-01", "2024-07-01"), ("hold", "2024-07-01", "2026-10-01")]
FIN = 0.0002


def oil_daily(d):
    """Oil day = NY day; ATR from 18:00-17:00 sessions (tday), known before the day."""
    ny = d.utc.dt.tz_convert("America/New_York")
    d = d.assign(tday=(ny + pd.Timedelta(hours=7)).dt.date)
    g = d.groupby("tday")
    D = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "o": g.o.first()})
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    return d, D


def intraday(d, D, cost, start_hm, k_bars, mode, exit_hm, weekday=None, floor=0.3):
    out = []
    ny = d.utc.dt.tz_convert("America/New_York")
    d = d.assign(wd=ny.dt.weekday)
    for day, x in d[(d.hm >= start_hm) & (d.hm <= exit_hm)].groupby("date"):
        if weekday is not None and x.wd.iloc[0] != weekday: continue
        if x.hm.iloc[0] != start_hm or len(x) < k_bars + 2: continue
        td = day
        a = D.atr.get(td, np.nan)
        if np.isnan(a): continue
        r0 = x.iloc[:k_bars]
        o0, c0, hi, lo = r0.o.iloc[0], r0.c.iloc[-1], r0.h.max(), r0.l.min()
        if c0 == o0: continue
        mv = 1 if c0 > o0 else -1
        dr = mv if mode == "mom" else -mv
        rest = x.iloc[k_bars:]; e = rest.o.iloc[0]
        if mode == "mom": st = lo if dr == 1 else hi
        else: st = (lo if dr == 1 else hi) - dr * 0.1 * a        # fade: stop beyond the reaction's extreme
        if (e - st) * dr < floor * a: st = e - dr * floor * a
        risk = (e - st) * dr
        px = None
        for b in rest.itertuples():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = st; break
            if b.hm >= exit_hm: px = b.c; break
        if px is None: px = rest.c.iloc[-1]
        out.append(dict(entry_time=rest.utc.iloc[0], r=((px - e) * dr - cost) / risk))
    return pd.DataFrame(out)


def trend(sym, days):
    from indices import DATA
    d = pd.read_csv(f"{DATA}\\FT_{sym}_H1.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'H1'").iloc[0]
    cost = 2 * meta.spread_med * meta.point
    d, D = oil_daily(d)
    D["hh"] = D.h.rolling(days).max().shift(1); D["ll"] = D.l.rolling(days).min().shift(1)
    ny = d.utc.dt.tz_convert("America/New_York"); wd = ny.dt.weekday.values; hr = (ny.dt.hour + ny.dt.minute / 60).values
    HH, LL, A = d.tday.map(D.hh).values, d.tday.map(D.ll).values, d.tday.map(D.atr).values
    o, h, l, c = d.o.values, d.h.values, d.l.values, d.c.values
    out, pos = [], None
    for i in range(1, len(d)):
        fri = wd[i] == 4 and hr[i] + 1 > 16.8 and hr[i] < 18
        if pos is not None:
            dd = pos["dir"]
            if (dd == 1 and l[i] <= pos["stop"]) or (dd == -1 and h[i] >= pos["stop"]):
                px = min(o[i], pos["stop"]) if dd == 1 else max(o[i], pos["stop"])
            elif fri: px = c[i]
            else:
                pos["best"] = max(pos["best"], h[i]) if dd == 1 else min(pos["best"], l[i])
                ns = pos["best"] - dd * 3 * A[i]
                pos["stop"] = max(pos["stop"], ns) if dd == 1 else min(pos["stop"], ns)
                continue
            nights = (d.utc.iloc[i] - pos["t"]).days
            out.append(dict(entry_time=pos["t"], r=((px - pos["e"]) * dd - cost - nights * FIN * pos["e"]) / pos["risk"]))
            pos = None; continue
        if np.isnan(HH[i]) or np.isnan(A[i]) or fri or (wd[i] == 4 and hr[i] >= 12): continue
        up, dn = h[i] > HH[i], l[i] < LL[i]
        if up == dn: continue
        dd = 1 if up else -1; lvl = HH[i] if up else LL[i]
        e = max(o[i], lvl) if up else min(o[i], lvl)
        pos = dict(dir=dd, e=e, stop=e - dd * 2 * A[i], risk=2 * A[i], best=e, t=d.utc.iloc[i])
    return pd.DataFrame(out)


VARIANTS = {}
for mode in ("mom", "fade"):
    for kb, lab in ((1, "15m"), (2, "30m")):
        for ex, exl in ((855, "14:15"), (720, "12:00")):
            VARIANTS[f"EIA {mode} {lab} exit{exl}"] = ("E", dict(start_hm=630, k_bars=kb, mode=mode, exit_hm=ex, weekday=2))
VARIANTS["NYMEX open 15m mom"] = ("N", dict(start_hm=540, k_bars=1, mode="mom", exit_hm=855))
VARIANTS["NYMEX open 30m mom"] = ("N", dict(start_hm=540, k_bars=2, mode="mom", exit_hm=855))
VARIANTS["trend 20d"] = ("T", dict(days=20))
VARIANTS["trend 55d"] = ("T", dict(days=55))


def job(a):
    sym, name = a
    kind, kw = VARIANTS[name]
    if kind == "T":
        t = trend(sym, **kw)
    else:
        d, cost = load(sym); d, D = oil_daily(d)
        t = intraday(d, D, cost * (1.5 if kind == "E" else 1.0), **kw)
    t["sym"], t["name"] = sym, name
    return t


if __name__ == "__main__":
    jobs = list(itertools.product(["USOIL.cash", "UKOIL.cash"], VARIANTS))
    with Pool(14) as p:
        res = p.map(job, jobs)
    t = pd.concat([x for x in res if len(x)])
    gb = gold_bad()
    t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values.astype(bool)
    t.to_pickle("oil_trades.pkl")
    rows = []
    for (sym, name), s in t.groupby(["sym", "name"]):
        row = dict(sym=sym, name=name)
        for p, a, b in PERIODS + ([("2016-21", "2016-01-01", "2022-01-01")] if name.startswith("trend") else []):
            x = s[(s.entry_time >= a) & (s.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p] = f"{x.r.sum():+6.1f}R n={len(x):3d} PF={pf:4.2f}"
        row["gold BAD"] = round(s.r[s.gbad].sum(), 1)
        rows.append(row)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(pd.DataFrame(rows).sort_values(["name", "sym"]).to_string(index=False))
