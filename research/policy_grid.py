"""Risk-policy grid for the challenge (goal: pass in 30-60 days, never breach FTMO 10% total / 5% daily).
Trades: real EA (half-risk BAD mode, MetaQuotes 2010-2026), each unit's R; BAD-regime units weighted 0.5.
Sizing: risk = clamp((guard + balance) / divisor, 0.25, cap) x weight, from the worst-case balance.
Entry allowed only if closed day loss + open risk + new risk <= daily guard, same for total guard.
Breach check (FTMO) on closed balance after every exit, with stress: every stop-out loses `slip` R extra."""
import sys, itertools, warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F

def trades():
    t = pd.read_csv("mt5_bm_halfrisk.csv", sep=";")
    ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    t["entry_time"], t["exit_time"] = ny(t.entry_time_ny), ny(t.exit_time_ny)
    t = t.dropna(subset=["entry_time", "exit_time"]).reset_index(drop=True)
    pp = pd.read_csv("paper_bm_halfrisk.csv", sep=";")
    pp["x"] = ny(pp.exit_ny); pp = pp.dropna(subset=["x"]).sort_values("x")
    ex = pp.x.values.astype("datetime64[ns]"); cum = np.r_[0, np.cumsum(pp.r.values)]
    e = t.entry_time.values.astype("datetime64[ns]")
    hi = np.searchsorted(ex, e); lo = np.searchsorted(ex, e - np.timedelta64(60, "D"))
    t["w"] = np.where((hi - lo >= 5) & (cum[hi] - cum[lo] < 0), 0.5, 1.0)
    t["stop"] = t.r < -0.5
    return t[["entry_time", "exit_time", "r", "w", "stop"]]

def run(t, ev, days, start, cap, div, T, D, hz, slip, target=10.0, min_days=4):
    end = start + pd.Timedelta(days=hz)
    bal, open_risk, day, day_start, tdays = 0.0, {}, None, 0.0, set()
    for (ts, kind, k), d in zip(ev, days):
        if ts < start: continue
        if ts > end: break
        if d != day: day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                r = t.r.iat[k] - (slip if t.stop.iat[k] else 0.0)
                bal += r * open_risk.pop(k)
                if -bal >= 10 or day_start - bal >= 5: return "BREACH"
                if bal >= target and len(tdays) >= min_days: return "pass"
            continue
        worst = bal - sum(open_risk.values())
        risk = max(min(cap, (T + worst) / div), 0.25) * t.w.iat[k]
        exposed = sum(open_risk.values())
        if -bal + exposed + risk > T:
            if not open_risk and -bal + risk > T: return "stuck"
            continue
        if (day_start - bal) + exposed + risk > D: continue
        open_risk[k] = risk; tdays.add(d)
    return "open"

PREP = {}
def init():
    t = trades(); tt, ev, days = F.prepare(t); PREP["x"] = (tt, ev, days)
def job(a):
    cap, div, T, slip = a
    tt, ev, days = PREP["x"]; D = T / 2
    out = []
    for s in STARTS:
        for hz in (30, 60):
            if s + pd.Timedelta(days=hz) < pd.Timestamp("2026-09-15", tz="UTC"):
                out.append((cap, div, T, slip, hz, s, run(tt, ev, days, s, cap, div, T, D, hz, slip)))
    return out
STARTS = [s for s in pd.date_range("2010-09-01", "2026-06-01", freq="4D", tz=F.PRAGUE) if s.weekday() < 5]
if __name__ == "__main__":
    grid = list(itertools.product([1.0, 1.25, 1.5, 1.75, 2.0], [3, 4, 5], [5.0, 6.0, 7.0, 8.0], [0.0, 0.5, 1.0]))
    with Pool(14, initializer=init) as p:
        res = [r for chunk in p.imap_unordered(job, grid) for r in chunk]
    d = pd.DataFrame(res, columns=["cap", "div", "T", "slip", "hz", "start", "res"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-26"])
    d.to_pickle("policy_grid.pkl")
    s0 = d[d.slip == 0]
    tab = s0.pivot_table(index=["cap", "div", "T"], columns="hz", values="res", aggfunc=lambda x: (x == "pass").mean()).add_prefix("pass")
    tab["stuck60"] = s0[s0.hz == 60].groupby(["cap", "div", "T"]).res.apply(lambda x: (x == "stuck").mean())
    for sl in (0.5, 1.0):
        tab[f"breach60 slip{sl}"] = d[(d.slip == sl) & (d.hz == 60)].groupby(["cap", "div", "T"]).res.apply(lambda x: (x == "BREACH").mean())
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
    print(tab.round(3).to_string())
