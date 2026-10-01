"""Third strategy search (FTMO data). Each candidate uses its own market's session structure.
Opening drive (indices): first W minutes after the local cash open set the direction; entry next bar; stop at the
window's opposite extreme (floor F x cash-session ATR); exit before the local cash close.
  GER40 (Xetra 09:00-17:30 Frankfurt, exit 17:15), UK100 (LSE 08:00-16:30 London, exit 16:15),
  JP225 (TSE 09:00-15:30 Tokyo, exit 15:15; TSE closed 15:00 until Nov 2024 -> exit 14:45 then), EU50 (as GER40).
London breakout of the Asian range (FX, fx.strat_L): USDJPY, EURUSD, GBPUSD, exit 12:00 / 16:00 London.
Cost = 2 x median FTMO spread. R per trade. dev 2021-09..2024-06, hold 2024-07..2026-09, FX also 2015-2021."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
MKTS = {"GER40.cash": ("Europe/Berlin", 540, 1035), "EU50.cash": ("Europe/Berlin", 540, 1035),
        "UK100.cash": ("Europe/London", 480, 975), "JP225.cash": ("Asia/Tokyo", 540, 915)}


def load_idx(sym, tz, open_hm, exit_hm):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_M15.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    loc = d.utc.dt.tz_convert(tz)
    d["date"], d["hm"] = loc.dt.date, loc.dt.hour * 60 + loc.dt.minute
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'M15'").iloc[0]
    cost = 2 * meta.spread_med * meta.point
    d = d[(d.hm >= open_hm) & (d.hm < exit_hm + 15)].rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})
    return d, cost


def opening_drive(sym, W=15, floor=0.3):
    tz, open_hm, exit_hm = MKTS[sym]
    d, cost = load_idx(sym, tz, open_hm, exit_hm)
    days = {k: x.reset_index(drop=True) for k, x in d.groupby("date") if x.hm.iloc[0] == open_hm and len(x) >= (exit_hm - open_hm) // 15 - 4}
    D = pd.DataFrame({k: dict(h=x.h.max(), l=x.l.min(), c=x.c.iloc[-1]) for k, x in days.items()}).T.astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    k = W // 15; out = []
    for day, x in days.items():
        a = D.atr[day]
        if np.isnan(a): continue
        ex_hm = exit_hm
        if sym == "JP225.cash" and pd.Timestamp(day) < pd.Timestamp("2024-11-05"): ex_hm = 885
        f = x.iloc[:k]; o0, c0, hi, lo = f.o.iloc[0], f.c.iloc[-1], f.h.max(), f.l.min()
        if c0 == o0: continue
        dr = 1 if c0 > o0 else -1
        rest = x.iloc[k:]; e = rest.o.iloc[0]
        st = lo if dr == 1 else hi
        if (e - st) * dr < floor * a: st = e - dr * floor * a
        risk = (e - st) * dr; px = xt = None
        for b in rest.itertuples():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px, xt = st, b.utc; break
            if b.hm >= ex_hm: px, xt = b.c, b.utc + pd.Timedelta(minutes=15); break
        if px is None: px, xt = rest.c.iloc[-1], rest.utc.iloc[-1]
        out.append(dict(entry_time=rest.utc.iloc[0], exit_time=xt, r=((px - e) * dr - cost) / risk))
    return pd.DataFrame(out)


def london(sym, exit_hm):
    import fx
    return fx.strat_L(sym, exit_hm)


JOBS = [("OD", s, dict(W=w, floor=f)) for s in MKTS for w in (15, 30) for f in (0.2, 0.3, 0.5)]
JOBS += [("LB", s, dict(exit_hm=x)) for s in ("USDJPY", "EURUSD", "GBPUSD") for x in (720, 960)]


def job(j):
    kind, sym, kw = j
    t = opening_drive(sym, **kw) if kind == "OD" else london(sym, **kw)
    t["name"] = f"{sym} {'opening drive' if kind == 'OD' else 'London BO'} {kw}"
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
        for p, a, b in [("2015-21 (FX only)", "2015-01-01", "2021-09-01"), ("dev 21-09..24-06", "2021-09-01", "2024-07-01"), ("hold 24-07..26-09", "2024-07-01", "2026-10-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            if not len(x): row[p] = ""; continue
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p] = f"{x.r.sum():+6.1f}R n={len(x):4d} PF={pf:4.2f}"
        x = t[t.entry_time >= "2021-09-01"]
        row["gold BAD (21-26)"] = round(x.r[x.gbad].sum(), 1)
        rows.append(row)
    pd.concat(allt).to_pickle("third_trades.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(pd.DataFrame(rows).to_string(index=False))
