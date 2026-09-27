"""Funded plan with a profit cushion: every 30 days pay out only the balance above C% (the rest stays as a
buffer against the 10% / 5% limits). 12 months from every weekly start since 2010. 14 worker processes."""
import itertools, warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
from policy_grid import trades

STARTS = list(pd.date_range("2010-09-01", "2025-09-01", freq="7D", tz=F.PRAGUE))


def run(t, ev, days, start, cap, T, C, slip, months=12):
    end = start + pd.Timedelta(days=30 * months)
    bal, open_risk, day, day_start, paid, nextpay = 0.0, {}, None, 0.0, 0.0, start + pd.Timedelta(days=30)
    for (ts, kind, k), d in zip(ev, days):
        if ts < start: continue
        if ts > end: break
        while ts >= nextpay:
            if bal > C and not open_risk: paid += bal - C; bal = C
            nextpay += pd.Timedelta(days=30)
        if d != day: day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                bal += (t.r.iat[k] - (slip if t.stop.iat[k] else 0.0)) * open_risk.pop(k)
                if -bal >= 10 or day_start - bal >= 5: return "BREACH", paid
            continue
        worst = bal - sum(open_risk.values())
        risk = max(min(cap, (T + worst) / 4), 0.25 * cap / 1.25) * t.w.iat[k]
        exposed = sum(open_risk.values())
        if -bal + exposed + risk > T:
            if not open_risk and -bal + risk > T: return "dead", paid
            continue
        if (day_start - bal) + exposed + risk > T / 2: continue
        open_risk[k] = risk
    return "alive", paid + max(bal - C, 0)


PREP = {}
def init(): PREP["x"] = F.prepare(trades())
def job(a):
    cap, T, C, slip = a; t, ev, days = PREP["x"]
    return [(cap, T, C, slip, s, *run(t, ev, days, s, cap, T, C, slip)) for s in STARTS]


if __name__ == "__main__":
    grid = list(itertools.product([0.5, 0.75, 1.0, 1.25], [7.0, 8.0], [0.0, 3.0, 5.0], [0.0, 1.0]))
    with Pool(14, initializer=init) as p:
        res = [r for c in p.imap_unordered(job, grid) for r in c]
    d = pd.DataFrame(res, columns=["cap", "T", "C", "slip", "start", "res", "paid"])
    d["era"] = pd.cut(d.start.dt.year, [2009, 2014, 2019, 2022, 2026], labels=["2010-14", "2015-19", "2020-22", "2023-25"])
    d.to_pickle("funded_cushion.pkl")
    s0 = d[d.slip == 0]
    k = ["cap", "T", "C"]
    tab = s0.groupby(k).apply(lambda x: pd.Series({"dead_12m": (x.res == "dead").mean(), "mean_payout": x.paid.mean() * 0.8,
                                                    "median_payout": np.median(x.paid) * 0.8, "zero_payout": (x.paid <= 0).mean()}))
    tab["dead 2020-22"] = s0[s0.era == "2020-22"].groupby(k).res.apply(lambda x: (x == "dead").mean())
    tab["dead 2023-25"] = s0[s0.era == "2023-25"].groupby(k).res.apply(lambda x: (x == "dead").mean())
    tab["breach slip1R"] = d[d.slip == 1].groupby(k).res.apply(lambda x: (x == "BREACH").mean())
    pd.set_option("display.width", 250)
    print(tab.round(3).to_string())
