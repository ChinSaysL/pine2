"""US index strategies designed from documented index behaviour (not the gold breakout). FTMO data.

A  Opening-range momentum (Zarattini & Aziz 2023): first 15/30 min after the 09:30 NY cash open; trade in
   that candle's direction from the next bar, stop at its opposite extreme, exit 15:55 NY (or +10R).
B  Late-day momentum (Gao et al. 2018; Baltussen et al. 2021 - hedging flows): at 15:30 NY trade the sign of
   the move since the previous 16:00 close (if larger than k x daily ATR), exit 16:00; stop 0.25 daily ATR.
C  Turn of the month (month-end inflows): buy the 15:45 NY bar of trading day -1 (or -2), sell 15:45 on day +3,
   stop 2 daily ATR, financing 0.02% of price per night.
D  Opening gap fade: 09:30 open gaps > k x daily ATR away from the previous 16:00 close -> fade toward it,
   target half the gap filled, stop the gap size beyond the open, exit 12:00 NY.
All costs = 2 x the median FTMO spread. R per trade. Dev 2022-07..2024-06, holdout 2024-07..2026-09.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
SYMS = ["US500.cash", "US100.cash", "US30.cash", "US2000.cash"]
PERIODS = [("dev", "2022-07-01", "2024-07-01"), ("hold", "2024-07-01", "2026-10-01")]
FIN = 0.0002


def load(sym, tf="M15"):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_{tf}.csv")
    d["utc"] = pd.to_datetime(d.utc, utc=True)
    ny = d.utc.dt.tz_convert("America/New_York")
    d["date"] = ny.dt.date
    d["hm"] = ny.dt.hour * 60 + ny.dt.minute
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == @tf").iloc[0]
    cost = 2 * meta.spread_med * meta.point
    return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"}), cost


def daily(d):
    """Cash-session days: 09:30-16:00 NY. Close = the 15:45 bar's close (16:00). ATR from those days."""
    cash = d[(d.hm >= 570) & (d.hm < 960)]
    g = cash.groupby("date")
    D = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.size()})
    D = D[D.n >= 20]
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)     # known before the day
    D["pc"] = D.c.shift(1)
    return D


def strat_A(d, D, cost, minutes=15, tgt=None):
    out = []
    by = dict(tuple(d[(d.hm >= 570) & (d.hm < 960)].groupby("date")))
    k = minutes // 15
    for day, x in by.items():
        if day not in D.index or len(x) < 20 or x.hm.iloc[0] != 570: continue
        first = x.iloc[:k]
        o0, c0, hi, lo = first.o.iloc[0], first.c.iloc[-1], first.h.max(), first.l.min()
        if c0 == o0: continue
        dr = 1 if c0 > o0 else -1
        rest = x.iloc[k:]
        e = rest.o.iloc[0]; st = lo if dr == 1 else hi; risk = (e - st) * dr
        if risk <= 0: continue
        tp = e + dr * tgt * risk if tgt else None
        px = None
        for _, b in rest.iterrows():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = st; break
            if tp is not None and ((dr == 1 and b.h >= tp) or (dr == -1 and b.l <= tp)): px = tp; break
            if b.hm >= 945: px = b.c; break
        if px is None: px = rest.c.iloc[-1]
        out.append(dict(entry_time=rest.utc.iloc[0], r=((px - e) * dr - cost) / risk))
    return pd.DataFrame(out)


def strat_B(d, D, cost, kmin=0.0):
    out = []
    x = d.set_index(["date", "hm"])
    for day in D.index:
        try:
            b = x.loc[(day, 930)]; last = x.loc[(day, 945)]
        except KeyError: continue
        pc, a = D.pc[day], D.atr[day]
        if np.isnan(pc) or np.isnan(a): continue
        mv = b.o - pc
        if abs(mv) < kmin * a or mv == 0: continue
        dr = int(np.sign(mv)); e = b.o; risk = 0.25 * a; st = e - dr * risk
        lo, hi = min(b.l, last.l), max(b.h, last.h)
        px = st if ((dr == 1 and lo <= st) or (dr == -1 and hi >= st)) else last.c
        out.append(dict(entry_time=b.utc, r=((px - e) * dr - cost) / risk))
    return pd.DataFrame(out)


def strat_C(d, D, cost, entry_day=-1, exit_day=3):
    out = []
    days = list(D.index); ym = pd.Series([(t.year, t.month) for t in days], index=days)
    months = sorted(set(ym))
    x = d.set_index(["date", "hm"])
    for (y, m) in months:
        cur = [t for t in days if ym[t] == (y, m)]
        nxt = [t for t in days if ym[t] == ((y, m + 1) if m < 12 else (y + 1, 1))]
        if len(cur) < 5 or len(nxt) < exit_day: continue
        ed, xd = cur[entry_day], nxt[exit_day - 1]
        try:
            eb = x.loc[(ed, 945)]; xb = x.loc[(xd, 945)]
        except KeyError: continue
        a = D.atr[ed]
        if np.isnan(a): continue
        e = eb.c; st = e - 2 * a; risk = 2 * a
        span = d[(d.utc > eb.utc) & (d.utc <= xb.utc)]
        px = st if (span.l <= st).any() else xb.c
        nights = (pd.Timestamp(xd) - pd.Timestamp(ed)).days
        out.append(dict(entry_time=eb.utc, r=((px - e) - cost - nights * FIN * e) / risk))
    return pd.DataFrame(out)


def strat_D(d, D, cost, kgap=0.5):
    out = []
    by = dict(tuple(d[(d.hm >= 570) & (d.hm < 720)].groupby("date")))
    for day, x in by.items():
        if day not in D.index or x.hm.iloc[0] != 570: continue
        pc, a = D.pc[day], D.atr[day]
        if np.isnan(pc) or np.isnan(a): continue
        gap = x.o.iloc[0] - pc
        if abs(gap) < kgap * a: continue
        dr = -int(np.sign(gap)); e = x.o.iloc[0]; risk = abs(gap); st = e - dr * risk; tp = e + dr * 0.5 * abs(gap)
        px = None
        for _, b in x.iterrows():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = st; break
            if (dr == 1 and b.h >= tp) or (dr == -1 and b.l <= tp): px = tp; break
        if px is None: px = x.c.iloc[-1]
        out.append(dict(entry_time=x.utc.iloc[0], r=((px - e) * dr - cost) / risk))
    return pd.DataFrame(out)


VARIANTS = {
    "A ORB15 EOD": ("A", dict(minutes=15)), "A ORB30 EOD": ("A", dict(minutes=30)),
    "A ORB15 10R": ("A", dict(minutes=15, tgt=10)), "A ORB30 10R": ("A", dict(minutes=30, tgt=10)),
    "B late mom k0": ("B", dict(kmin=0.0)), "B late mom k0.5": ("B", dict(kmin=0.5)), "B late mom k1": ("B", dict(kmin=1.0)),
    "C TOM -1..+3": ("C", dict(entry_day=-1, exit_day=3)), "C TOM -2..+3": ("C", dict(entry_day=-2, exit_day=3)),
    "C TOM -1..+4": ("C", dict(entry_day=-1, exit_day=4)),
    "D gap fade 0.5": ("D", dict(kgap=0.5)), "D gap fade 1.0": ("D", dict(kgap=1.0)),
}
FN = {"A": strat_A, "B": strat_B, "C": strat_C, "D": strat_D}


def gold_bad():
    from regime import regime_flag, paper_trades
    from oldgold import load_full
    g = load_full("XAUUSD", f"{DATA}\\XAUUSD_H1.csv")
    return pd.Series(regime_flag(g, paper_trades(g)), index=g.time)


def job(a):
    sym, name = a
    d, cost = load(sym); D = daily(d)
    kind, kw = VARIANTS[name]
    t = FN[kind](d, D, cost, **kw)
    t["sym"], t["name"] = sym, name
    return t


if __name__ == "__main__":
    jobs = list(itertools.product(SYMS, VARIANTS))
    with Pool(14) as p:
        res = p.map(job, jobs)
    t = pd.concat([x for x in res if len(x)])
    gb = gold_bad()
    t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values.astype(bool)
    t.to_pickle("indices_trades.pkl")
    rows = []
    for (sym, name), s in t.groupby(["sym", "name"]):
        row = dict(sym=sym, name=name)
        for p, a, b in PERIODS:
            x = s[(s.entry_time >= a) & (s.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p] = f"{x.r.sum():+6.1f}R n={len(x):3d} PF={pf:4.2f}"
        row["gold BAD"] = round(s.r[s.gbad].sum(), 1)
        rows.append(row)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(pd.DataFrame(rows).sort_values(["name", "sym"]).to_string(index=False))
