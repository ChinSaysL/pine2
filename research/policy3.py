"""Account risk policy for the 3-engine live system (gold + Nasdaq opening + Nasdaq noise; FTMO EA trades).
Grid: cap {1.0,1.25,1.5}%, divisor {3,4,5}, total guard {6,7,8}% (daily = half), near-target protection {none, 0.5x
risk from +7%, from +8%}. Fresh challenge from every start day Oct 2021 - Jun 2026. Breach stress: +0.5R / +1R
extra slippage on every stop. 14 workers."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from third_combo import gold_bad_at
from final_summary import book


def sim(t, ev, days, start, horizon, cap, div, T, D, protect, slip=0.0, target=10.0):
    end = start + pd.Timedelta(days=horizon)
    bal, open_risk, day, day_start, tdays = 0.0, {}, None, 0.0, set()
    for (ts, kind, k), d in zip(ev, days):
        if ts < start: continue
        if ts > end: break
        if d != day: day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                bal += (t.r.iat[k] - (slip if t.stop.iat[k] else 0.0)) * open_risk.pop(k)
                if -bal >= 10 or day_start - bal >= 5: return "BREACH"
                if bal >= target and len(tdays) >= 4: return "pass"
            continue
        worst = bal - sum(open_risk.values())
        risk = max(min(cap, (T + worst) / div), 0.25) * t.w.iat[k]
        if protect and bal >= protect: risk *= 0.5
        exposed = sum(open_risk.values())
        if -bal + exposed + risk > T:
            if not open_risk and -bal + risk > T: return "stuck"
            continue
        if (day_start - bal) + exposed + risk > D: continue
        open_risk[k] = risk; tdays.add(d)
    return "open"


GRID = list(itertools.product([1.0, 1.25, 1.5], [3, 4, 5], [6.0, 7.0, 8.0], [0, 7.0, 8.0]))
STARTS = S.STARTS[::2]
PREP = {}
def init():
    t = book(); PREP["x"] = (t,) + F.prepare(t)[1:]
def job(p):
    cap, div, T, prot = p; t, ev, days = PREP["x"]
    out = []
    for s in STARTS:
        row = dict(cap=cap, div=div, T=T, prot=prot, start=s)
        for h in (30, 60, 90):
            row[f"r{h}"] = sim(t, ev, days, s, h, cap, div, T, T / 2, prot)
        row["stress05"] = sim(t, ev, days, s, 60, cap, div, T, T / 2, prot, slip=0.5)
        row["stress1"] = sim(t, ev, days, s, 60, cap, div, T, T / 2, prot, slip=1.0)
        out.append(row)
    return out


if __name__ == "__main__":
    init()
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame([r for c in p.imap_unordered(job, GRID) for r in c])
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    res.to_pickle("policy3.pkl")
    k = ["cap", "div", "T", "prot"]
    f = lambda col, v: res.groupby(k)[col].apply(lambda x: (x == v).mean())
    tab = pd.DataFrame({"pass30": f("r30", "pass"), "pass60": f("r60", "pass"), "pass90": f("r90", "pass"), "stuck90": f("r90", "stuck"),
                        "p60 gold-BAD": res[res.bad].groupby(k).r60.apply(lambda x: (x == "pass").mean()),
                        "BREACH +0.5R": f("stress05", "BREACH"), "BREACH +1R": f("stress1", "BREACH")}).round(3)
    live = tab.loc[(1.25, 4, 7.0, 0)]
    print("LIVE (1.25 / 4 / 7% / no protection):", live.to_dict())
    safe = tab[(tab["BREACH +1R"] == 0)]
    print(f"\n{len(safe)} of {len(tab)} policies never breach FTMO even with +1R slippage on every stop. Top 15 by pass60 among them:")
    pd.set_option("display.width", 250); print(safe.sort_values("pass60", ascending=False).head(15).to_string())
    print("\nEffect of near-target protection (average over the other settings):"); print(tab.groupby("prot")[["pass30", "pass60", "pass90", "stuck90"]].mean().round(3).to_string())
    print("\nEffect of the total guard:"); print(tab.groupby("T")[["pass30", "pass60", "pass90", "stuck90", "BREACH +1R"]].mean().round(3).to_string())
    print("\nEffect of the cap:"); print(tab.groupby("cap")[["pass30", "pass60", "pass90", "stuck90", "BREACH +1R"]].mean().round(3).to_string())
