"""Event-driven FTMO challenge simulator.

Each trade list (entry_time, exit_time, r, stream) is replayed from many start days. Positions can
overlap (several streams). A trade is only opened when the day's closed loss + the full risk of
every open trade + its own risk stays under the internal daily limit, and likewise for the total
limit - so neither FTMO limit can be breached short of a gap through a stop.

Pass: balance >= +target with >= min_days trading days. Fail: the account can no longer open a
trade under the internal max loss limit (or an actual FTMO breach, which the guards prevent).
"""
import numpy as np
import pandas as pd

PRAGUE = "Europe/Prague"


def prepare(trades):
    t = trades.copy()
    t["entry_time"] = pd.to_datetime(t.entry_time, utc=True)
    t["exit_time"] = pd.to_datetime(t.exit_time, utc=True)
    t = t.sort_values("entry_time").reset_index(drop=True)
    ev = []
    for k, row in t.iterrows():
        # At one timestamp: other trades' closes (0), then opens (1), then the close of a trade that
        # opened and closed inside that same bar (2) - which must come after its own open.
        ev.append((row.entry_time, 1, k))
        ev.append((row.exit_time, 2 if row.exit_time == row.entry_time else 0, k))
    ev.sort(key=lambda e: (e[0], e[1]))
    ev = [(ts, 0 if kind == 2 else kind, k) for ts, kind, k in ev]
    days = [e[0].tz_convert(PRAGUE).date() for e in ev]
    return t, ev, days


def run_challenge(t, ev, days, start, risk_fn, horizon_days=30, target=10.0, int_daily=4.0, int_total=8.0,
                  min_days=4):
    end = start + pd.Timedelta(days=horizon_days)
    bal = 0.0
    open_risk = {}
    day, day_start = None, 0.0
    tdays = set()
    for (ts, kind, k), d in zip(ev, days):
        if ts < start:
            continue
        if ts > end:
            break
        if d != day:
            day, day_start = d, bal
        if kind == 0:
            if k in open_risk:
                bal += t.r.iat[k] * open_risk.pop(k)
                if bal >= target and len(tdays) >= min_days:
                    return "pass", (ts - start).total_seconds() / 86400
            continue
        risk = risk_fn(bal - sum(open_risk.values()))       # size from the worst case balance
        if "w" in t.columns:                                # signal-quality weight, capped
            risk = min(risk * t.w.iat[k], t.wcap.iat[k] if "wcap" in t.columns else 99)
        exposed = sum(open_risk.values())
        if -bal + exposed + risk > int_total:
            if not open_risk and -bal + risk > int_total:
                return "fail", (ts - start).total_seconds() / 86400
            continue
        if (day_start - bal) + exposed + risk > int_daily:
            continue
        open_risk[k] = risk
        tdays.add(d)
    return "open", horizon_days


def fixed(p):
    return lambda bal: p


def scaled(cap, n, floor=0.25, int_total=8.0):
    return lambda bal: max(min(cap, (int_total + bal) / n), floor)


def pass_rates(trades, schemes, horizons=(30, 60), step_days=1, **limits):
    t, ev, days = prepare(trades)
    first = t.entry_time.min().tz_convert(PRAGUE).normalize()
    last = t.exit_time.max().tz_convert(PRAGUE).normalize()
    out = []
    for name, fn in schemes.items():
        row = dict(scheme=name)
        for hz in horizons:
            starts = [first + pd.Timedelta(days=i) for i in range(0, (last - first).days - hz + 1, step_days)]
            starts = [s for s in starts if s.weekday() < 5]
            res = [run_challenge(t, ev, days, s, fn, horizon_days=hz, **limits) for s in starts]
            row[f"pass{hz}"] = np.mean([r[0] == "pass" for r in res])
            row[f"fail{hz}"] = np.mean([r[0] == "fail" for r in res])
            p = [r[1] for r in res if r[0] == "pass"]
            row[f"med_days{hz}"] = float(np.median(p)) if p else float("nan")
        out.append(row)
    return pd.DataFrame(out)
