"""Indecisive-candle filter for the Nasdaq opening trade: skip when the 09:30-09:45 candle's body < B x its range.
Neighbours B = 0 (live), 0.1 ... 0.4. R by era, then FTMO odds with gold v2 + noise engine (EA trades). 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from third_combo import gold_bad_at

BS = [0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4]
PREP = {}


def ea_trades():
    t = pd.read_csv("mt5_nq_noise.csv", sep=";")
    ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    t["entry_time"], t["exit_time"] = ny(t.entry_time_ny), ny(t.exit_time_ny)
    t = t.dropna(subset=["entry_time", "exit_time"])
    t["date"] = t.entry_time.dt.tz_convert("America/New_York").dt.date
    t["kind"] = np.where(t.comment.str.contains("NOISE"), "noise", "orb")
    diag = pd.read_pickle("nq_diag.pkl"); body = dict(zip(diag.day.dt.date, diag.body_frac))
    t["body"] = t.date.map(body)
    return t


def init():
    t = ea_trades()
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    for B in BS:
        keep = (t.kind == "noise") | (t.body.fillna(1) >= B)
        n = t[keep].assign(w=0.75, stop=lambda x: x.r < -0.5, mkt="nasdaq")[["entry_time", "exit_time", "r", "w", "stop", "mkt"]]
        b = pd.concat([g, n]).sort_values("entry_time").reset_index(drop=True)
        PREP[B] = (b,) + F.prepare(b)[1:]


def job(a):
    B, s = a; t, ev, days = PREP[B]; out = dict(B=B, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"wd{h}"] = p, st, w
    return out


def month(a):
    B, s = a; t, ev, days = PREP[B]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(B=B, start=s, pnl=b)


if __name__ == "__main__":
    t = ea_trades(); o = t[t.kind == "orb"].copy(); o["y"] = pd.to_datetime(o.date).dt.year
    print("OPENING TRADE (EA, fixed 1%) - R by year when skipping candles with body < B x range")
    rows = []
    for B in BS:
        x = o[o.body.fillna(1) >= B]
        r = {"B": B, "trades": len(x), "total R": round(x.r.sum(), 1), "PF": round(x.r[x.r > 0].sum() / -x.r[x.r < 0].sum(), 2)}
        r.update(x.groupby("y").r.sum().round(1).to_dict()); rows.append(r)
    pd.set_option("display.width", 250); print(pd.DataFrame(rows).to_string(index=False))
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(BS, S.STARTS)), chunksize=30))
        mo = pd.DataFrame(p.map(month, list(itertools.product(BS, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "21-23", "24-26")
    mo["y"] = mo.start.dt.tz_convert("Europe/Prague").dt.year
    g = res.groupby("B"); gm = mo.groupby("B")
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "p60 21-23": res[res.era == "21-23"].groupby("B").pass60.mean(), "p60 24-26": res[res.era == "24-26"].groupby("B").pass60.mean(),
                        "p60 gold-BAD": res[res.bad].groupby("B").pass60.mean(), "avg month %": gm.pnl.mean(),
                        "2026 avg month %": mo[mo.y == 2026].groupby("B").pnl.mean(), "2026 months +": mo[mo.y == 2026].groupby("B").pnl.apply(lambda v: (v > 0).mean()),
                        "worst day": g.wd90.min()})
    print("\nWITH GOLD + NOISE ENGINE (live policy, FTMO challenge sim)"); print(tab.round(3).to_string())
