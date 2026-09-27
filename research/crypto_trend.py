"""Crypto multi-day trend following (BTC, ETH, SOL; FTMO H1). Rules fixed in advance.
T1 Donchian: daily close (00:00 UTC) above the prior N-day high -> long (below the N-day low -> short), entry next hour;
   stop 2 x daily ATR, trailing k x daily ATR from the best close; N 20 / 55, k 3 / 4.
T2 Time-series momentum: sign of the last L-day return (L 30 / 60) at each daily close; hold that side, exit on a sign
   flip or a 3 x daily ATR trailing stop.
Variants long/short and long-only. News rule: flat 75 min before FOMC (14:00 NY) and NFP (first Friday 08:30 NY),
re-enter the next hour after the release if the position's signal still holds (costs charged again).
Costs: max(2 x median spread, 0.05%) per entry/exit + 30%/yr financing per day held.
Leverage 1:3.3 -> notional capped at 1x equity at 1.25% risk (R scaled). R per trade.
Periods: dev 2017-2021, hold 2022-2024, 2025-26."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
from newfam import FOMC


def news_times(start, end):
    ev = [pd.Timestamp(f"{x} 14:00", tz="America/New_York") for x in FOMC]
    for m in pd.date_range(start, end, freq="MS"):
        d = m + pd.offsets.Week(weekday=4) if m.weekday() != 4 else m
        ev.append(pd.Timestamp(f"{d.date()} 08:30", tz="America/New_York"))
    return sorted(e.tz_convert("UTC") for e in ev)


def load(sym):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_H1.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d[d.utc >= "2017-01-01"].reset_index(drop=True)
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'H1'").iloc[0]
    cost = max(2 * meta.spread_med * meta.point / d.close.median(), 0.0005)
    d["day"] = d.utc.dt.date
    g = d.groupby("day")
    D = pd.DataFrame({"h": g.high.max(), "l": g.low.min(), "c": g.close.last()})
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return d, D, cost


def run(sym, kind="T1", N=20, k=3.0, L=30, long_only=False):
    d, D, cost = load(sym)
    if kind == "T1":
        hh, ll = D.h.rolling(N).max().shift(1), D.l.rolling(N).min().shift(1)
        sig = pd.Series(np.where(D.c > hh, 1, np.where(D.c < ll, -1, 0)), index=D.index)       # entry trigger
    else:
        sig = np.sign(np.log(D.c).diff(L)).fillna(0)                                             # state
    if long_only: sig = sig.clip(lower=0)
    ev = news_times(d.utc.iat[0], d.utc.iat[-1]); ev_idx = 0
    days = list(D.index); first_hour = d.groupby("day").head(1).index
    out, pos = [], None
    first_of_day = {d.day.iat[i]: i for i in first_hour}

    def close(i, px, why):
        nonlocal pos
        held = (d.utc.iat[i] - pos["t"]).total_seconds() / 86400
        r = ((px - pos["e"]) * pos["dir"] - cost * pos["e"] - 0.30 / 365 * held * pos["e"]) / pos["risk"]
        scale = min(1.0, (pos["risk"] / pos["e"]) / 0.0125)
        out.append(dict(entry_time=pos["t"], exit_time=d.utc.iat[i], r=r * scale, why=why, dir=pos["dir"]))
        pos = None

    for di in range(max(N, L) + 15, len(days) - 1):
        day, nxt = days[di], days[di + 1]
        if nxt not in first_of_day: continue
        i0 = first_of_day[nxt]; i1 = first_of_day.get(days[di + 2], len(d)) if di + 2 < len(days) else len(d)
        a = D.atr.iat[di]; s = int(sig.iat[di])
        # daily decision at 00:00 UTC (bar i0 open)
        if pos is not None and ((kind == "T2" and s != pos["dir"]) or (kind == "T1" and False)):
            close(i0, d.open.iat[i0], "signal flip")
        if pos is None and s != 0:
            e = d.open.iat[i0]; risk = (2 if kind == "T1" else 3) * a
            pos = dict(dir=s, e=e, stop=e - s * risk, risk=risk, t=d.utc.iat[i0], best=e, trail=(k if kind == "T1" else 3) * a, sig=s)
        # walk the day's hours
        pending = None
        for i in range(i0, i1):
            t = d.utc.iat[i]
            while ev_idx < len(ev) and ev[ev_idx] < t: ev_idx += 1
            near = ev_idx < len(ev) and (ev[ev_idx] - t) <= pd.Timedelta(minutes=75)
            if pending is not None and i >= pending["at"]:
                kp = pending; pending = None
                if (kp["dir"] == 1 and d.open.iat[i] > kp["stop"]) or (kp["dir"] == -1 and d.open.iat[i] < kp["stop"]):
                    e = d.open.iat[i]
                    pos = dict(dir=kp["dir"], e=e, stop=kp["stop"], risk=abs(e - kp["stop"]), t=t, best=kp["best"], trail=kp["trail"], sig=kp["sig"])
            if pos is not None:
                dr = pos["dir"]
                if (dr == 1 and d.low.iat[i] <= pos["stop"]) or (dr == -1 and d.high.iat[i] >= pos["stop"]):
                    close(i, min(d.open.iat[i], pos["stop"]) if dr == 1 else max(d.open.iat[i], pos["stop"]), "stop"); continue
                pos["best"] = max(pos["best"], d.close.iat[i]) if dr == 1 else min(pos["best"], d.close.iat[i])
                ns = pos["best"] - dr * pos["trail"]
                pos["stop"] = max(pos["stop"], ns) if dr == 1 else min(pos["stop"], ns)
                if near:
                    pending = dict(dir=dr, stop=pos["stop"], trail=pos["trail"], best=pos["best"], sig=pos["sig"], at=i + 2)
                    close(i, d.open.iat[i], "news")
        if pending is not None and pos is None and i1 < len(d):
            kp = pending
            if (kp["dir"] == 1 and d.open.iat[i1 - 1] > kp["stop"]) or (kp["dir"] == -1 and d.open.iat[i1 - 1] < kp["stop"]):
                e = d.close.iat[i1 - 1]
                pos = dict(dir=kp["dir"], e=e, stop=kp["stop"], risk=abs(e - kp["stop"]), t=d.utc.iat[i1 - 1], best=kp["best"], trail=kp["trail"], sig=kp["sig"])
    return pd.DataFrame(out)


SYMS = ["BTCUSD", "ETHUSD", "SOLUSD"]
VARS = {}
for lo in (False, True):
    tag = " long-only" if lo else ""
    for N in (20, 55):
        for k in (3.0, 4.0):
            VARS[f"T1 Donchian {N}d trail {k:.0f}ATR{tag}"] = dict(kind="T1", N=N, k=k, long_only=lo)
    for L in (30, 60):
        VARS[f"T2 momentum {L}d{tag}"] = dict(kind="T2", L=L, long_only=lo)


def job(a):
    s, n = a
    t = run(s, **VARS[n]); t["name"] = f"{s} {n}"; t["sym"] = s; return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, list(itertools.product(SYMS, VARS)))
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
    pd.concat(allt).to_pickle("crypto_trend.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(pd.DataFrame(rows).to_string(index=False))
