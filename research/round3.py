"""Third-strategy search, round 3 (intraday, flat before the close, FTMO M15 data). Rules fixed in advance.

L  Lunch-break continuation (HK50: morning 09:30-12:00, afternoon 13:00-16:00 HKT; JP225: 09:00-11:30 / 12:30-15:30 JST,
   close 15:00 before 2024-11-05): trade the afternoon session in the morning session's direction (|morning| > m x
   cash ATR); enter at the afternoon open, stop 0.5 x cash ATR, exit 15 min before the close. Control: opposite.
F  First half-hour -> last half-hour (Jin et al. 2020, Gao et al. 2018): sign of the first 30 minutes' return ->
   trade the last 30 minutes (enter 30 min before the close, exit at the close), stop 0.5 x cash ATR. Control.
A  Agricultural previous-day momentum (CORN, WHEAT, SOYBEAN, COCOA, COFFEE, COTTON, SUGAR): yesterday's session moved
   > 0.5 x ATR and closed in the top/bottom 30% of its range -> trade today's session open -> last bar in that
   direction, stop 0.7 x ATR. Control: opposite.
Costs: 2 x median FTMO spread. R per trade. Periods: indices dev 2021-09..2023, hold 2024-2026; agri dev ..2024, hold 2025-26.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"


def load(sym, tz):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_M15.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d[d.utc >= "2021-09-01"] if "cash" in sym else d
    loc = d.utc.dt.tz_convert(tz); d["date"], d["hm"] = loc.dt.date, loc.dt.hour * 60 + loc.dt.minute
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'M15'").iloc[0]
    return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"}).reset_index(drop=True), 2 * meta.spread_med * meta.point


def cash_atr(days):
    D = pd.DataFrame({k: dict(h=x.h.max(), l=x.l.min(), c=x.c.iloc[-1]) for k, x in days.items()}).T.astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    return tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)


def walk(x, e, dr, st, exit_hm, cost, risk):
    for b in x.itertuples():
        if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): return ((st - e) * dr - cost) / risk
        if b.hm >= exit_hm: return ((b.c - e) * dr - cost) / risk
    return ((x.c.iat[-1] - e) * dr - cost) / risk


SESS = {"HK50.cash": ("Asia/Hong_Kong", 570, 720, 780, 960), "JP225.cash": ("Asia/Tokyo", 540, 690, 750, 930)}


def lunch(sym, m=0.0, side=1):
    tz, o1, c1, o2, c2 = SESS[sym]; d, cost = load(sym, tz)
    days = {k: x for k, x in d[(d.hm >= o1) & (d.hm < c2)].groupby("date") if x.hm.iat[0] == o1}
    atr = cash_atr(days); out = []
    for k, x in days.items():
        close = c2 if not (sym == "JP225.cash" and pd.Timestamp(k) < pd.Timestamp("2024-11-05")) else 900
        mo = x[x.hm < c1]; af = x[(x.hm >= o2) & (x.hm < close)]
        a = atr.get(k, np.nan)
        if len(mo) < 6 or len(af) < 6 or np.isnan(a): continue
        mv = mo.c.iat[-1] - mo.o.iat[0]
        if abs(mv) <= m * a or mv == 0: continue
        dr = int(np.sign(mv)) * side; e = af.o.iat[0]; risk = 0.5 * a
        out.append(dict(entry_time=af.utc.iat[0], r=walk(af, e, dr, e - dr * risk, close - 15, cost, risk)))
    return pd.DataFrame(out)


def firstlast(sym, side=1):
    tz, o1, c1, o2, c2 = SESS[sym]; d, cost = load(sym, tz)
    days = {k: x for k, x in d[(d.hm >= o1) & (d.hm < c2)].groupby("date") if x.hm.iat[0] == o1}
    atr = cash_atr(days); out = []
    for k, x in days.items():
        close = c2 if not (sym == "JP225.cash" and pd.Timestamp(k) < pd.Timestamp("2024-11-05")) else 900
        f = x[x.hm < o1 + 30]; last = x[(x.hm >= close - 30) & (x.hm < close)]
        a = atr.get(k, np.nan)
        if len(f) < 2 or len(last) < 2 or np.isnan(a): continue
        mv = f.c.iat[-1] - f.o.iat[0]
        if mv == 0: continue
        dr = int(np.sign(mv)) * side; e = last.o.iat[0]; risk = 0.5 * a
        out.append(dict(entry_time=last.utc.iat[0], r=walk(last, e, dr, e - dr * risk, 9999, cost, risk)))
    return pd.DataFrame(out)


AGRI = ["CORN.c", "WHEAT.c", "SOYBEAN.c", "COCOA.c", "COFFEE.c", "COTTON.c", "SUGAR.c"]


def agri(sym, side=1):
    d, cost = load(sym, "America/New_York")
    ny = d.utc.dt.tz_convert("America/New_York"); d["tday"] = (ny + pd.Timedelta(hours=7)).dt.date
    days = {k: x.reset_index(drop=True) for k, x in d.groupby("tday") if len(x) >= 8}
    keys = list(days)
    D = pd.DataFrame({k: dict(o=x.o.iat[0], h=x.h.max(), l=x.l.min(), c=x.c.iat[-1]) for k, x in days.items()}).T.astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    out = []
    for i in range(20, len(keys)):
        p, k = keys[i - 1], keys[i]
        y = D.loc[p]; a = y.atr; mv = y.c - y.o; rg = y.h - y.l
        if rg <= 0 or abs(mv) < 0.5 * a: continue
        pos = (y.c - y.l) / rg
        dr0 = 1 if (mv > 0 and pos >= 0.7) else (-1 if (mv < 0 and pos <= 0.3) else 0)
        if not dr0: continue
        x = days[k]; dr = dr0 * side; e = x.o.iat[0]; risk = 0.7 * a
        r = None
        for b in x.itertuples():
            if (dr == 1 and b.l <= e - dr * risk) or (dr == -1 and b.h >= e - dr * risk): r = (-risk - cost) / risk; break
        if r is None: r = ((x.c.iat[-1] - e) * dr - cost) / risk
        out.append(dict(entry_time=x.utc.iat[0], r=r))
    return pd.DataFrame(out)


JOBS = [("L", s, dict(m=m)) for s in SESS for m in (0.0, 0.3)] + [("L", s, dict(m=0.0, side=-1)) for s in SESS]
JOBS += [("F", s, {}) for s in SESS] + [("F", s, dict(side=-1)) for s in SESS]
JOBS += [("A", s, {}) for s in AGRI] + [("A", s, dict(side=-1)) for s in AGRI]


def job(j):
    k, s, kw = j
    t = lunch(s, **kw) if k == "L" else firstlast(s, **kw) if k == "F" else agri(s, **kw)
    lab = {"L": "lunch-break continuation", "F": "first->last half-hour", "A": "agri prev-day momentum"}[k]
    t["name"] = f"{lab} {s} {kw.get('m', '') if k == 'L' else ''}{' CONTROL(opposite)' if kw.get('side') == -1 else ''}"
    t["kind"] = k
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, JOBS)
    rows = []; allt = []
    for t in res:
        if not len(t): continue
        allt.append(t)
        split = "2025-01-01" if t.kind.iat[0] == "A" else "2024-01-01"
        row = {"name": t.name.iat[0]}
        for p_, a, b in [("dev", "2000-01-01", split), ("hold", split, "2027-01-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p_] = f"{x.r.sum():+7.1f}R n={len(x):4d} PF={pf:4.2f} avg={x.r.mean():+.3f}"
        rows.append(row)
    pd.concat(allt).to_pickle("round3_trades.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(pd.DataFrame(rows).to_string(index=False))
