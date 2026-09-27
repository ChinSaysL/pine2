"""Stats of the deployed system: gold EA v2 + Nasdaq ORB (only while gold is BAD), live risk policy
(cap 1.25%, divisor 4, guards 7% / 3.5%, gold BAD units at 0.5x). Real EA tester trades:
gold = mt5_bm_halfrisk.csv (MetaQuotes data), Nasdaq = mt5_nq_ftmo2.csv (FTMO data, 2021-09..2026-09).
Every window starts from a fresh account (like a new challenge) on every trading day. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from policy_grid import trades as gold_trades

CAP, DIV, T, D = 1.25, 4, 7.0, 3.5
START, END = pd.Timestamp("2021-10-01", tz="UTC"), pd.Timestamp("2026-09-18", tz="UTC")


def nasdaq():
    t = pd.read_csv("mt5_nq_ftmo2.csv", sep=";")
    ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    t["entry_time"], t["exit_time"] = ny(t.entry_time_ny), ny(t.exit_time_ny)
    t = t.dropna(subset=["entry_time", "exit_time"])
    pp = pd.read_csv("paper_bm_halfrisk.csv", sep=";")
    pp["x"] = ny(pp.exit_ny); pp = pp.dropna(subset=["x"]).sort_values("x")
    ex = pp.x.values.astype("datetime64[ns]"); cum = np.r_[0, np.cumsum(pp.r.values)]
    e = t.entry_time.dt.tz_convert(None).values.astype("datetime64[ns]")
    hi = np.searchsorted(ex, e); lo = np.searchsorted(ex, e - np.timedelta64(60, "D"))
    t = t[(hi - lo >= 5) & (cum[hi] - cum[lo] < 0)].copy()            # only while gold is BAD
    t["w"] = 1.0; t["stop"] = t.r < -0.5; t["mkt"] = "nasdaq"
    return t[["entry_time", "exit_time", "r", "w", "stop", "mkt"]]


def book():
    g = gold_trades(); g["mkt"] = "gold"
    return pd.concat([g[(g.entry_time >= START - pd.Timedelta(days=5))], nasdaq()]).sort_values("entry_time").reset_index(drop=True)


def sim(t, ev, days, start, horizon, target=None):
    """Fresh account from `start` for `horizon` days. Returns final %, max drawdown % (peak-to-trough of
    closed balance incl. the start), worst day %, passed?, stuck?, per-trade P&L list."""
    end = start + pd.Timedelta(days=horizon)
    bal, peak, mdd, open_risk, day, day_start, low = 0.0, 0.0, 0.0, {}, None, 0.0, 0.0
    worst_day, tdays, passed, stuck, pnl = 0.0, set(), False, False, []
    for (ts, kind, k), d in zip(ev, days):
        if ts < start: continue
        if ts > end: break
        if d != day:
            if day is not None: worst_day = min(worst_day, bal - day_start)
            day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                x = t.r.iat[k] * open_risk.pop(k); bal += x; pnl.append((t.mkt.iat[k], x))
                peak = max(peak, bal); mdd = max(mdd, peak - bal); low = min(low, bal)
                if target and bal >= target and len(tdays) >= 4: passed = True; break
            continue
        worst = bal - sum(open_risk.values())
        risk = max(min(CAP, (T + worst) / DIV), 0.25) * t.w.iat[k]
        exposed = sum(open_risk.values())
        if -bal + exposed + risk > T:
            if not open_risk and -bal + risk > T: stuck = True; break
            continue
        if (day_start - bal) + exposed + risk > D: continue
        open_risk[k] = risk; tdays.add(d)
    worst_day = min(worst_day, bal - day_start)
    return bal, mdd, worst_day, passed, stuck, pnl, low


PREP = {}
def init():
    t = book(); PREP["x"] = (t,) + F.prepare(t)[1:]

STARTS = [s for s in pd.date_range(START, END - pd.Timedelta(days=90), freq="1D") if s.weekday() < 5]
def job(s):
    t, ev, days = PREP["x"]
    out = {"start": s}
    for h in (1, 7, 30):
        b, m, w, _, _, pnl, lo = sim(t, ev, days, s, h)
        out[f"p{h}"], out[f"dd{h}"], out[f"wd{h}"], out[f"low{h}"] = b, m, w, lo
        if h == 30: out["pnl"] = pnl
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"cdd{h}"], out[f"clow{h}"], out[f"cwd{h}"] = p, st, m, lo, w
    return out


def daywin(t):
    t = t.copy(); t["d"] = t.exit_time.dt.tz_convert("Europe/Prague").dt.date
    x = t.groupby("d").apply(lambda g: (g.r * g.w).sum())
    return (x > 0).mean(), len(x)

if __name__ == "__main__":
    init()
    print("winning trading days (P&L > 0 among days with a closed trade): %.1f%% of %d days" % tuple([100 * daywin(book())[0], daywin(book())[1]]))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, STARTS, chunksize=20))
    res.to_pickle("stats_summary.pkl")
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "gold ranging 21-23", "gold trending 24-26")
    t = book()
    print("TRADES:", t.groupby("mkt").r.agg(["count", lambda x: (x > 0).mean(), "mean"]).round(3).to_string())
    for h in (1, 7, 30):
        x = res[f"p{h}"]
        print(f"\n{h}-day P&L %: mean {x.mean():+.2f} | median {x.median():+.2f} | 10th pct {x.quantile(.1):+.2f} | 90th pct {x.quantile(.9):+.2f} | "
              f"positive {(x > 0).mean():.0%} | zero {(x == 0).mean():.0%} | worst {x.min():+.2f} | best {x.max():+.2f} | "
              f"max DD inside window: median {res[f'dd{h}'].median():.2f} worst {res[f'dd{h}'].max():.2f} | worst single day {res[f'wd{h}'].min():+.2f}")
        print("   by era mean:", res.groupby("era")[f"p{h}"].mean().round(2).to_dict(), " positive:", res.groupby("era")[f"p{h}"].apply(lambda v: (v > 0).mean()).round(2).to_dict())
    for h in (30, 60, 90):
        print(f"\nPASS within {h}d: {res[f'pass{h}'].mean():.1%} (by era {res.groupby('era')[f'pass{h}'].mean().round(3).to_dict()}) | "
              f"stuck at -7% guard {res[f'stuck{h}'].mean():.1%} | lowest point vs start: median {res[f'clow{h}'].median():+.2f}%, 5th pct {res[f'clow{h}'].quantile(.05):+.2f}%, worst {res[f'clow{h}'].min():+.2f}% | worst day {res[f'cwd{h}'].min():+.2f}% | max DD inside challenge: median {res[f'cdd{h}'].median():.2f}%, 95th pct {res[f'cdd{h}'].quantile(.95):.2f}%, worst {res[f'cdd{h}'].max():.2f}%")
