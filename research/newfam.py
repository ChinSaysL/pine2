"""Three genuinely different families (not breakout, not mean reversion), FTMO H1 data, rules fixed in advance.

A  FX time-of-day (Breedon & Ranaldo 2013): a currency depreciates during its home trading hours.
   Sessions (NY time): Tokyo 19:00-03:00, Europe 03:00-08:00, US 08:00-16:00. Hold one session, stop 1 daily ATR.
     USDJPY long Tokyo / short US;  EURUSD, GBPUSD short Europe / long US;  USDCHF long Europe / short US;
     AUDUSD, NZDUSD short Tokyo / long US.
B  Pre-FOMC drift (Lucca & Moench 2015): long US500 / US100 from 14:00 NY the day before the statement to 14:00 NY
   on statement day (exit before the release), stop 1.5 daily ATR. Control: the same window on non-FOMC days.
C  Currency momentum (Menkhoff et al. 2012): every Monday 03:00 NY rank EUR, GBP, AUD, NZD, JPY, CHF vs USD by
   the last 21 (or 63) trading days; long the 2 strongest / short the 2 weakest vs USD, exit Friday 15:00 NY,
   stop 2 daily ATR per leg.
R per trade = P&L / stop distance, after 2 x median spread (+0.6 bp FX commission) and financing.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
FOMC = ["2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
        "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
        "2020-01-29", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
        "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
        "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
        "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
        "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16"]


def load(sym):
    d = pd.read_csv(f"{DATA}\\FT_{sym}_H1.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == @sym and tf == 'H1'").iloc[0]
    fx = len(sym) == 6
    cost = 2 * meta.spread_med * meta.point + (0.00006 * d.close.median() if fx else 0)
    ny = d.utc.dt.tz_convert("America/New_York")
    d["nyd"], d["nyh"], d["wd"] = ny.dt.date, ny.dt.hour, ny.dt.weekday
    d["tday"] = (ny + pd.Timedelta(hours=7)).dt.date
    g = d.groupby("tday")
    D = pd.DataFrame({"h": g.high.max(), "l": g.low.min(), "c": g.close.last()})
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    d["datr"] = d.tday.map(tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1))
    return d.reset_index(drop=True), cost, D.c


def hold(d, i0, i1, dr, stop_dist, cost, fin=0.0, nights=0):
    """Enter at bar i0's open, exit at bar i1's open (or stop inside)."""
    e = d.open.iat[i0]; st = e - dr * stop_dist
    for j in range(i0, i1):
        if (dr == 1 and d.low.iat[j] <= st) or (dr == -1 and d.high.iat[j] >= st):
            return ((st - e) * dr - cost - nights * fin * e) / stop_dist
    return ((d.open.iat[i1] - e) * dr - cost - nights * fin * e) / stop_dist


SESS = {"Tokyo": (19, 3), "Europe": (3, 8), "US": (8, 16)}
RULES = {"USDJPY": {"Tokyo": 1, "US": -1}, "EURUSD": {"Europe": -1, "US": 1}, "GBPUSD": {"Europe": -1, "US": 1},
         "USDCHF": {"Europe": 1, "US": -1}, "AUDUSD": {"Tokyo": -1, "US": 1}, "NZDUSD": {"Tokyo": -1, "US": 1}}


def fam_A(sym, sess):
    d, cost, _ = load(sym); dr = RULES[sym][sess]; h0, h1 = SESS[sess]
    starts = np.where((d.nyh == h0) & (d.wd != 4 if h0 == 19 else True))[0]
    out = []
    for i0 in starts:
        a = d.datr.iat[i0]
        if np.isnan(a): continue
        end = d.utc.iat[i0] + pd.Timedelta(hours=(h1 - h0) % 24)
        i1 = d.utc.searchsorted(end)
        if i1 >= len(d) or (d.utc.iat[i1] - end) > pd.Timedelta(hours=2): continue
        out.append(dict(entry_time=d.utc.iat[i0], exit_time=d.utc.iat[i1], r=hold(d, i0, i1, dr, a, cost)))
    return pd.DataFrame(out)


def fam_B(sym, control=False):
    d, cost, _ = load(sym); fomc = {pd.Timestamp(x).date() for x in FOMC}
    out = []
    idx14 = np.where(d.nyh == 14)[0]
    days = d.nyd.values
    for i0 in idx14:
        if d.wd.iat[i0] >= 4: continue
        nxt = [j for j in range(i0 + 1, min(i0 + 40, len(d))) if d.nyh.iat[j] == 14 and days[j] != days[i0]]
        if not nxt: continue
        i1 = nxt[0]
        is_f = days[i1] in fomc
        if is_f == control: continue
        a = d.datr.iat[i0]
        if np.isnan(a): continue
        out.append(dict(entry_time=d.utc.iat[i0], exit_time=d.utc.iat[i1], r=hold(d, i0, i1, 1, 1.5 * a, cost, 0.0002, 1)))
    return pd.DataFrame(out)


def fam_C(look):
    ccy = {"EUR": ("EURUSD", 1), "GBP": ("GBPUSD", 1), "AUD": ("AUDUSD", 1), "NZD": ("NZDUSD", 1), "JPY": ("USDJPY", -1), "CHF": ("USDCHF", -1)}
    L = {c: load(s) for c, (s, _) in ccy.items()}
    closes = pd.DataFrame({c: L[c][2] * 1.0 for c in ccy}).dropna()
    rets = pd.DataFrame({c: np.log(closes[c]).diff(look) * ccy[c][1] for c in ccy})
    out = []
    d0 = L["EUR"][0]
    mondays = d0[(d0.wd == 0) & (d0.nyh == 3)].utc
    for t in mondays:
        prev = [x for x in rets.index if pd.Timestamp(x) < t.tz_convert("America/New_York").tz_localize(None).normalize()]
        if len(prev) < look + 1: continue
        r = rets.loc[prev[-1]].dropna()
        if len(r) < 6: continue
        order = r.sort_values()
        picks = [(c, 1) for c in order.index[-2:]] + [(c, -1) for c in order.index[:2]]
        for c, side in picks:
            d, cost, _ = L[c]; sym_dir = side * ccy[c][1]
            i0 = d.utc.searchsorted(t)
            if i0 >= len(d) or abs((d.utc.iat[i0] - t).total_seconds()) > 3600: continue
            fri = d[(d.utc > t) & (d.wd == 4) & (d.nyh == 15)]
            if not len(fri) or (fri.utc.iat[0] - t).days > 5: continue
            i1 = fri.index[0]
            a = d.datr.iat[i0]
            if np.isnan(a): continue
            out.append(dict(entry_time=t, exit_time=d.utc.iat[i1], r=hold(d, i0, i1, sym_dir, 2 * a, cost, 0.00003, 4), leg=c))
    return pd.DataFrame(out)


JOBS = [("A", s, dict(sess=x)) for s in RULES for x in RULES[s]]
JOBS += [("B", s, dict(control=c)) for s in ("US500.cash", "US100.cash") for c in (False, True)]
JOBS += [("C", "FX", dict(look=l)) for l in (21, 63)]


def job(j):
    k, s, kw = j
    t = fam_A(s, **kw) if k == "A" else fam_B(s, **kw) if k == "B" else fam_C(**kw)
    if k == "A":
        t["name"] = f"A time-of-day {s} {kw['sess']} {'long' if RULES[s][kw['sess']] == 1 else 'short'}"
    elif k == "B":
        t["name"] = f"B pre-FOMC {s}{' (CONTROL: non-FOMC days)' if kw['control'] else ''}"
    else:
        t["name"] = f"C FX momentum {kw['look']}d"
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
        for p, a, b in [("dev 2015/18-2021", "2000-01-01", "2022-01-01"), ("hold 2022-2026", "2022-01-01", "2027-01-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p] = f"{x.r.sum():+7.1f}R n={len(x):4d} PF={pf:4.2f} avg={x.r.mean():+.3f}"
        row["gold BAD"] = round(t.r[t.gbad].sum(), 1)
        rows.append(row)
    pd.concat(allt).to_pickle("newfam_trades.pkl")
    pd.set_option("display.width", 260)
    print(pd.DataFrame(rows).to_string(index=False))
