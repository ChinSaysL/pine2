"""Funded-account plan: 12 months from every start since 2010, profits paid out every 30 days (balance reset
to the initial; FTMO keeps the 10% / 5% limits relative to the initial balance). 'Dead' = the internal guard
stops trading for good (or a stressed FTMO breach). Reports survival, payouts (80% split) per year."""
import itertools, warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from policy_grid import trades

def run(t, ev, days, start, cap, div, T, D, slip, months=12):
    end = start + pd.Timedelta(days=30 * months)
    bal, open_risk, day, day_start, paid, nextpay = 0.0, {}, None, 0.0, 0.0, start + pd.Timedelta(days=30)
    for (ts, kind, k), d in zip(ev, days):
        if ts < start: continue
        if ts > end: break
        while ts >= nextpay:
            if bal > 0 and not open_risk: paid += bal; bal = 0.0
            nextpay += pd.Timedelta(days=30)
        if d != day: day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                bal += (t.r.iat[k] - (slip if t.stop.iat[k] else 0.0)) * open_risk.pop(k)
                if -bal >= 10 or day_start - bal >= 5: return "BREACH", paid
            continue
        worst = bal - sum(open_risk.values())
        risk = max(min(cap, (T + worst) / div), 0.25 * cap / 1.25) * t.w.iat[k]
        exposed = sum(open_risk.values())
        if -bal + exposed + risk > T:
            if not open_risk and -bal + risk > T: return "dead", paid
            continue
        if (day_start - bal) + exposed + risk > D: continue
        open_risk[k] = risk
    return "alive", paid + max(bal, 0)

PREP = {}
def init():
    PREP["x"] = F.prepare(trades())
def job(a):
    cap, T, slip = a
    t, ev, days = PREP["x"]
    return [(cap, T, slip, s, *run(t, ev, days, s, cap, 4, T, T / 2, slip)) for s in STARTS]
STARTS = [s for s in pd.date_range("2010-09-01", "2025-09-01", freq="7D", tz=F.PRAGUE)]
if __name__ == "__main__":
    grid = list(itertools.product([0.5, 0.75, 1.0, 1.25, 1.5], [5.0, 7.0, 8.0], [0.0, 1.0]))
    with Pool(14, initializer=init) as p:
        res = [r for c in p.imap_unordered(job, grid) for r in c]
    d = pd.DataFrame(res, columns=["cap", "T", "slip", "start", "res", "paid"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-25"])
    s0 = d[d.slip == 0]
    tab = s0.groupby(["cap", "T"]).apply(lambda x: pd.Series({
        "dead_12m": (x.res == "dead").mean(), "median_payout_%/yr": np.median(x.paid) * 0.8, "mean_payout_%/yr": x.paid.mean() * 0.8,
        "zero_payout_share": (x.paid <= 0).mean()}))
    tab["breach_slip1R"] = d[d.slip == 1].groupby(["cap", "T"]).res.apply(lambda x: (x == "BREACH").mean())
    tab["dead 2020-22"] = s0[s0.era == "2020-22"].groupby(["cap", "T"]).res.apply(lambda x: (x == "dead").mean())
    tab["payout 2020-22"] = s0[s0.era == "2020-22"].groupby(["cap", "T"]).paid.mean() * 0.8
    pd.set_option("display.width", 250); print(tab.round(3).to_string())
