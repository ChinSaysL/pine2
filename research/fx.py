"""Forex strategies designed from FX market structure (FTMO data).

L  London breakout of the Asian range: range 00:00-07:00 London (M15); OCO stops at range +-10% from 07:00 to
   11:00 London; stop at the opposite side (floor 0.3 daily ATR); exit 12:00 or 16:00 London.
M  Month-end fix flows (Melvin & Prins 2015): last trading day of the month, if US500 beat GER40 month-to-date,
   foreign investors sell USD into the 16:00 London (WM/R) fix -> short USD from 12:00 London, exit 16:00 London;
   otherwise long USD. Stop 0.5 daily ATR. H1, 2015+.
G  Gotobi (Japanese importers buy USD before the 09:55 JST Tokyo fix on the 5th/10th/15th/20th/25th/month-end,
   earlier business day if on a weekend): long USDJPY 08:00 -> 10:00 JST. Stop 0.3 daily ATR. H1, 2015+.
A  Quiet-Asia mean reversion on calm crosses: 19:00-02:00 NY, M15 close outside the 20-bar 2.0 (2.5) sd band ->
   fade to the band middle, stop 1 band-width beyond, exit 02:00 NY at the latest.
Costs: 2 x median FTMO spread + 0.6 bp commission. R per trade.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"


def load(sym, tf):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_{tf}.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == @tf").iloc[0]
    cost = 2 * meta.spread_med * meta.point + 0.00006 * d.c.median()
    lon = d.utc.dt.tz_convert("Europe/London"); ny = d.utc.dt.tz_convert("America/New_York"); jp = d.utc.dt.tz_convert("Asia/Tokyo")
    d["lon_date"], d["lon_hm"] = lon.dt.date, lon.dt.hour * 60 + lon.dt.minute
    d["ny_date"], d["ny_hm"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute
    d["jp_date"], d["jp_hm"] = jp.dt.date, jp.dt.hour * 60 + jp.dt.minute
    d["tday"] = (ny + pd.Timedelta(hours=7)).dt.date
    g = d.groupby("tday")
    D = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    d["datr"] = d.tday.map(D.atr)
    return d, cost


def run_path(bars, dr, e, st, tp, cost):
    risk = (e - st) * dr
    for b in bars.itertuples():
        if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): return ((st - e) * dr - cost) / risk
        if tp is not None and ((dr == 1 and b.h >= tp) or (dr == -1 and b.l <= tp)): return ((tp - e) * dr - cost) / risk
    return ((bars.c.iloc[-1] - e) * dr - cost) / risk


def strat_L(sym, exit_hm):
    d, cost = load(sym, "M15"); out = []
    for day, x in d.groupby("lon_date"):
        asia = x[x.lon_hm < 420]; sess = x[(x.lon_hm >= 420) & (x.lon_hm < exit_hm)]
        if len(asia) < 20 or len(sess) < 8: continue
        a = x.datr.iloc[-1]
        if np.isnan(a): continue
        hi, lo = asia.h.max(), asia.l.min(); rg = hi - lo; up, dn = hi + 0.1 * rg, lo - 0.1 * rg
        win = sess[sess.lon_hm < 660]
        for k, b in enumerate(win.itertuples()):
            u, w = b.h >= up, b.l <= dn
            if u and w: break
            if u or w:
                dr = 1 if u else -1; e = max(b.o, up) if u else min(b.o, dn)
                st = lo if dr == 1 else hi
                if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
                out.append(dict(entry_time=b.utc, r=run_path(sess.iloc[k:], dr, e, st, None, cost))); break
    return pd.DataFrame(out)


def strat_M(sym):
    d, cost = load(sym, "H1")
    idx = {}
    for s in ("US500.cash", "GER40.cash"):
        x = pd.read_csv(f"{DATA}\\FT_{s}_H1.csv"); x["utc"] = pd.to_datetime(x.utc, utc=True)
        idx[s] = x.set_index("utc").close
    us_dollar_base = sym.startswith("USD")
    out = []
    days = sorted(d.lon_date.unique()); ser = pd.Series(days)
    ym = pd.Series([pd.Timestamp(t).year * 100 + pd.Timestamp(t).month for t in days])
    last_days = ser.groupby(ym.values).max().values
    for day in last_days:
        x = d[d.lon_date == day]
        ent = x[x.lon_hm == 720]; ex = x[(x.lon_hm > 720) & (x.lon_hm <= 960)]
        if not len(ent) or not len(ex): continue
        t0 = ent.utc.iloc[0]; m0 = pd.Timestamp(t0.year, t0.month, 1, tz="UTC")
        try:
            r = {s: idx[s][:t0].iloc[-1] / idx[s][:m0].iloc[-1] - 1 for s in idx}
        except IndexError: continue
        usd = -1 if r["US500.cash"] > r["GER40.cash"] else 1        # -1 = sell USD into the fix
        dr = usd if us_dollar_base else -usd
        e = ent.o.iloc[0]; a = ent.datr.iloc[0]
        if np.isnan(a): continue
        st = e - dr * 0.5 * a
        bars = pd.concat([ent, ex[ex.lon_hm < 960]])
        out.append(dict(entry_time=t0, r=run_path(bars, dr, e, st, None, cost)))
    return pd.DataFrame(out)


def gotobi_days(dates):
    import calendar
    s = set()
    for y in range(2015, 2027):
        for m in range(1, 13):
            last = calendar.monthrange(y, m)[1]
            for dd in (5, 10, 15, 20, 25, last):
                t = pd.Timestamp(y, m, dd)
                while t.weekday() >= 5: t -= pd.Timedelta(days=1)
                s.add(t.date())
    return s


def strat_G(sym="USDJPY"):
    d, cost = load(sym, "H1"); gd = gotobi_days(None); out = []
    for day, x in d.groupby("jp_date"):
        if day not in gd: continue
        ent = x[x.jp_hm == 480]; ex = x[(x.jp_hm >= 480) & (x.jp_hm < 600)]
        if not len(ent): continue
        e = ent.o.iloc[0]; a = ent.datr.iloc[0]
        if np.isnan(a): continue
        out.append(dict(entry_time=ent.utc.iloc[0], r=run_path(ex, 1, e, e - 0.3 * a, None, cost)))
    return pd.DataFrame(out)


def strat_A(sym, k):
    d, cost = load(sym, "M15")
    mid = d.c.rolling(20).mean(); sd = d.c.rolling(20).std()
    d["mid"], d["up"], d["dn"] = mid, mid + k * sd, mid - k * sd
    night = (d.ny_hm >= 1140) | (d.ny_hm < 120)
    out = []; i = 20; n = len(d)
    c, o, h, l = d.c.values, d.o.values, d.h.values, d.l.values
    while i < n - 1:
        if night[i] and d.ny_hm.iat[i] != 105 and (c[i] > d.up.iat[i] or c[i] < d.dn.iat[i]):
            dr = -1 if c[i] > d.up.iat[i] else 1
            e = o[i + 1]; tp = d.mid.iat[i]; st = e - dr * (d.up.iat[i] - d.dn.iat[i]) / 2
            j = i + 1; px = None
            while j < n:
                if (dr == 1 and l[j] <= st) or (dr == -1 and h[j] >= st): px = st; break
                if (dr == 1 and h[j] >= tp) or (dr == -1 and l[j] <= tp): px = tp; break
                if not night[j] or d.ny_hm.iat[j] == 105: px = c[j]; break
                j += 1
            if px is not None and (e - st) * dr > 0:
                out.append(dict(entry_time=d.utc.iat[i + 1], r=((px - e) * dr - cost) / ((e - st) * dr)))
            i = j + 1; continue
        i += 1
    return pd.DataFrame(out)


JOBS = [("L", s, dict(exit_hm=x)) for s in ("EURUSD", "GBPUSD", "USDJPY", "EURJPY", "GBPJPY") for x in (720, 960)]
JOBS += [("M", s, {}) for s in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY")]
JOBS += [("G", "USDJPY", {})]
JOBS += [("A", s, dict(k=k)) for s in ("EURGBP", "EURCHF", "AUDNZD", "EURUSD") for k in (2.0, 2.5)]
FN = {"L": strat_L, "M": strat_M, "G": strat_G, "A": strat_A}


def job(j):
    kind, sym, kw = j
    t = FN[kind](sym, **kw) if kind != "G" else strat_G(sym)
    t["name"] = f"{kind} {sym} {kw}"
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, JOBS)
    from indices import gold_bad
    gb = gold_bad()
    rows = []
    for t in res:
        if not len(t): continue
        t["gbad"] = gb.reindex(pd.DatetimeIndex(t.entry_time).floor("h")).fillna(False).values.astype(bool)
        row = {"name": t.name.iloc[0]}
        for p, a, b in [("2015-19", "2015-01-01", "2020-01-01"), ("2020-22H1", "2020-01-01", "2022-07-01"), ("dev 22H2-24H1", "2022-07-01", "2024-07-01"), ("hold 24H2-26", "2024-07-01", "2026-10-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            if not len(x): continue
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p] = f"{x.r.sum():+6.1f}R n={len(x):3d} PF={pf:4.2f}"
        row["gold BAD"] = round(t.r[t.gbad].sum(), 1)
        rows.append(row)
    pd.set_option("display.width", 260)
    print(pd.DataFrame(rows).fillna("").to_string(index=False))
