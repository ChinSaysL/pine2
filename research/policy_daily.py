"""Which FTMO limit breaks under stress, and does a tighter daily guard fix it? Live cap 1.25 / div 4 / total 7%."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from third_combo import gold_bad_at
from final_summary import book

def sim(t, ev, days, start, horizon, cap, div, T, D, slip=0.0, target=10.0):
    end = start + pd.Timedelta(days=horizon)
    bal, open_risk, day, day_start, tdays = 0.0, {}, None, 0.0, set()
    for (ts, kind, k), d in zip(ev, days):
        if ts < start: continue
        if ts > end: break
        if d != day: day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                bal += (t.r.iat[k] - (slip if t.stop.iat[k] else 0.0)) * open_risk.pop(k)
                if day_start - bal >= 5: return "BREACH daily"
                if -bal >= 10: return "BREACH total"
                if bal >= target and len(tdays) >= 4: return "pass"
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

GRID = [(1.25, 4, 7.0, 3.5), (1.25, 4, 7.0, 2.5), (1.25, 4, 8.0, 2.5), (1.25, 4, 8.0, 2.75), (1.25, 4, 7.5, 2.5), (1.25, 4, 8.5, 2.5)]
PREP = {}
def init():
    t = book(); PREP["x"] = (t,) + F.prepare(t)[1:]
def job(a):
    p, s = a; t, ev, days = PREP["x"]; cap, div, T, D = p
    out = dict(p=f"cap {cap} / div {div} / total {T}% / daily {D}%", start=s)
    for h in (30, 60, 90): out[f"r{h}"] = sim(t, ev, days, s, h, cap, div, T, D)
    for sl in (0.25, 0.5, 1.0): out[f"s{sl}"] = sim(t, ev, days, s, 60, cap, div, T, D, slip=sl)
    return out
if __name__ == "__main__":
    init()
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(GRID, S.STARTS)), chunksize=40))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    order = list(dict.fromkeys(res.p)); g = res.groupby("p")
    f = lambda c, v: g[c].apply(lambda x: x.astype(str).str.startswith(v).mean())
    tab = pd.DataFrame({"pass30": f("r30", "pass"), "pass60": f("r60", "pass"), "pass90": f("r90", "pass"), "stuck90": f("r90", "stuck"),
                        "p60 gold-BAD": res[res.bad].groupby("p").r60.apply(lambda x: (x == "pass").mean()),
                        "breach +0.25R": f("s0.25", "BREACH"), "breach +0.5R": f("s0.5", "BREACH"), "breach +1R": f("s1.0", "BREACH"),
                        "+1R daily": f("s1.0", "BREACH daily"), "+1R total": f("s1.0", "BREACH total")}).reindex(order)
    pd.set_option("display.width", 250); print(tab.round(3).to_string())
