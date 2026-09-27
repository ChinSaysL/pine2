"""Crypto strategies (BTC, ETH, SOL only; FTMO M15 data), crypto-specific mechanisms, rules fixed in advance.

T  Intraday time-series momentum (Shen, Urquhart & Wang 2022): sign of the first 30 min of the UTC day
   (00:00-00:30) -> trade the last 30 min (23:30-24:00 UTC). Stop 1% (catastrophe), exit at 24:00 UTC.
L  Liquidation-cascade reversal: a 15-min bar with return beyond k x the sd of the last 96 bars' returns (k 4 / 5)
   -> fade it from the next bar; target the bar's midpoint, stop 0.25 x bar range beyond its extreme, exit after 4 h.
G  CME weekend gap: gap = price at Sun 18:00 NY (CME reopen) - price at Fri 17:00 NY (CME close); |gap| >= g x daily
   ATR (g 0.5 / 1.0) -> fade toward Friday's close (target), stop 1 x gap beyond the entry, max 48 h.
S  Session drift: long during US hours (09:30-16:00 NY), or short during Asia hours (20:00-04:00 NY); stop 2%.
Every family has an opposite-side CONTROL. FTMO crypto leverage 1:3.3 -> notional capped at 1x equity at 1.25% risk
(tighter stops are sized down: R scaled). Cost = max(2 x median spread, 0.05%) of price + 30%/yr financing per 24 h.
Periods: dev 2017-2021, hold 2022-2026 (SOL: 2025-26 only).
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
RISK = 0.0125
FIN_DAY = 0.30 / 365


def load(sym):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_M15.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d[d.utc >= "2017-01-01"].reset_index(drop=True)
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'M15'").iloc[0]
    cost_rel = max(2 * meta.spread_med * meta.point / d.close.median(), 0.0005)
    ny = d.utc.dt.tz_convert("America/New_York")
    d["ny_hm"], d["ny_wd"], d["ny_date"] = ny.dt.hour * 60 + ny.dt.minute, ny.dt.weekday, ny.dt.date
    d["u_hm"], d["u_date"] = d.utc.dt.hour * 60 + d.utc.dt.minute, d.utc.dt.date
    g = d.groupby("u_date")
    D = pd.DataFrame({"h": g.high.max(), "l": g.low.min(), "c": g.close.last()})
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    d["datr"] = d.u_date.map(tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1))
    return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"}), cost_rel


def settle(d, i0, dr, e, st, tp, i_end, cost_rel):
    """Walk bars i0..i_end-1; return (R, exit index)."""
    risk = abs(e - st); px = None; j = i0
    for j in range(i0, min(i_end, len(d))):
        if (dr == 1 and d.l.iat[j] <= st) or (dr == -1 and d.h.iat[j] >= st): px = st; break
        if tp is not None and ((dr == 1 and d.h.iat[j] >= tp) or (dr == -1 and d.l.iat[j] <= tp)): px = tp; break
    if px is None: j = min(i_end, len(d)) - 1; px = d.c.iat[j]
    days = (d.utc.iat[j] - d.utc.iat[i0]).total_seconds() / 86400
    r = ((px - e) * dr - cost_rel * e - (FIN_DAY * e * days if days >= 0.5 else 0)) / risk
    scale = min(1.0, (risk / e) / RISK)            # 1x equity notional cap at 1.25% risk (leverage 1:3.3)
    return r * scale, j


def fam_T(sym, side=1):
    d, cr = load(sym); out = []
    for day, x in d.groupby("u_date"):
        f = x[x.u_hm < 30]; last = x[x.u_hm >= 1410]
        if len(f) < 2 or len(last) < 2: continue
        mv = f.c.iat[-1] - f.o.iat[0]
        if mv == 0: continue
        dr = int(np.sign(mv)) * side; i0 = last.index[0]; e = d.o.iat[i0]
        r, _ = settle(d, i0, dr, e, e * (1 - dr * 0.01), None, last.index[-1] + 1, cr)
        out.append(dict(entry_time=d.utc.iat[i0], r=r))
    return pd.DataFrame(out)


def fam_L(sym, k=4.0, side=1):
    d, cr = load(sym)
    ret = np.log(d.c).diff(); sd = ret.rolling(96).std().shift(1)
    z = (ret / sd).values; out = []; i = 100
    while i < len(d) - 20:
        if abs(z[i]) >= k:
            dr = -int(np.sign(z[i])) * side
            hi, lo = d.h.iat[i], d.l.iat[i]; rg = hi - lo; e = d.o.iat[i + 1]
            if side == 1:
                st = (lo - 0.25 * rg) if dr == 1 else (hi + 0.25 * rg); tp = (hi + lo) / 2
            else:
                st = e - dr * (0.5 * rg + 0.25 * rg); tp = e + dr * 0.5 * rg
            if (e - st) * dr <= 0 or (tp - e) * dr <= 0: i += 1; continue
            r, j = settle(d, i + 1, dr, e, st, tp, i + 1 + 16, cr)
            out.append(dict(entry_time=d.utc.iat[i + 1], r=r)); i = j + 1; continue
        i += 1
    return pd.DataFrame(out)


def fam_G(sym, g=0.5, side=1):
    d, cr = load(sym); out = []
    fri = d[(d.ny_wd == 4) & (d.ny_hm == 16 * 60 + 45)]
    for fi in fri.index:
        ref = d.c.iat[fi]
        sun = d[(d.index > fi) & (d.ny_wd == 6) & (d.ny_hm == 18 * 60)]
        if not len(sun): continue
        si = sun.index[0]
        if (d.utc.iat[si] - d.utc.iat[fi]).days > 3: continue
        e = d.o.iat[si]; gap = e - ref; a = d.datr.iat[si]
        if np.isnan(a) or abs(gap) < g * a: continue
        dr = -int(np.sign(gap)) * side
        tp = ref if side == 1 else e + dr * abs(gap); st = e - dr * abs(gap)
        r, _ = settle(d, si, dr, e, st, tp, si + 192, cr)
        out.append(dict(entry_time=d.utc.iat[si], r=r))
    return pd.DataFrame(out)


def fam_S(sym, sess="US", side=1):
    d, cr = load(sym); out = []
    if sess == "US": start, end, dr0 = 570, 960, 1
    else: start, end, dr0 = 1200, 240, -1
    starts = d.index[(d.ny_hm == start) & (d.ny_wd < 5 if sess == "US" else d.ny_wd.isin([6, 0, 1, 2, 3]))]
    for i0 in starts:
        dur = ((end - start) % 1440) // 15
        dr = dr0 * side; e = d.o.iat[i0]
        r, _ = settle(d, i0, dr, e, e * (1 - dr * 0.02), None, i0 + dur, cr)
        out.append(dict(entry_time=d.utc.iat[i0], r=r))
    return pd.DataFrame(out)


SYMS = ["BTCUSD", "ETHUSD", "SOLUSD"]
JOBS = []
for s in SYMS:
    JOBS += [("T", s, {}), ("T", s, dict(side=-1))]
    JOBS += [("L", s, dict(k=k)) for k in (4.0, 5.0)] + [("L", s, dict(k=4.0, side=-1))]
    JOBS += [("G", s, dict(g=g)) for g in (0.5, 1.0)] + [("G", s, dict(g=0.5, side=-1))]
    JOBS += [("S", s, dict(sess="US")), ("S", s, dict(sess="Asia")), ("S", s, dict(sess="US", side=-1))]
LAB = {"T": "first->last 30min momentum", "L": "liquidation reversal", "G": "CME weekend gap fade", "S": "session drift"}


def job(j):
    k, s, kw = j
    t = {"T": fam_T, "L": fam_L, "G": fam_G, "S": fam_S}[k](s, **kw)
    extra = " ".join(f"{a}={b}" for a, b in kw.items() if a != "side")
    t["name"] = f"{s} {LAB[k]} {extra}{' CONTROL(opposite)' if kw.get('side') == -1 else ''}"
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, JOBS)
    rows = []; allt = []
    for t in res:
        if not len(t): continue
        allt.append(t); row = {"name": t.name.iat[0]}
        for p_, a, b in [("dev 2017-21", "2017-01-01", "2022-01-01"), ("hold 2022-24", "2022-01-01", "2025-01-01"), ("2025-26", "2025-01-01", "2027-01-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            if not len(x): row[p_] = ""; continue
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p_] = f"{x.r.sum():+7.1f}R n={len(x):4d} PF={pf:4.2f}"
        rows.append(row)
    pd.concat(allt).to_pickle("crypto_trades.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(pd.DataFrame(rows).to_string(index=False))
