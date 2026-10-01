"""FTMO challenge replay from a trade list expressed in R.

Usage: python ftmo_sim.py trades.csv [cost_R]

Rules modelled (FTMO 2-step, Challenge phase):
  * profit target +10% of the initial balance, at least 4 trading days
  * max daily loss 5% of initial balance (day = midnight Prague), open losses count
  * max loss 10% of initial balance
The strategy's own guards are modelled too: a trade is only opened when its full risk
still fits under the internal limits (4% daily / 8% total by default).
"""
import sys
import numpy as np
import pandas as pd

path = sys.argv[1]
cost_r = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0

df = pd.read_csv(path, sep=";")
df["entry_time"] = pd.to_datetime(df["entry_time"]).dt.tz_localize("UTC")
df["exit_time"] = pd.to_datetime(df["exit_time"]).dt.tz_localize("UTC")
df["r"] = df["r"] - cost_r
df["day"] = df["exit_time"].dt.tz_convert("Europe/Prague").dt.date
df["month"] = df["exit_time"].dt.tz_convert("Europe/Prague").dt.strftime("%Y-%m")

r = df["r"].to_numpy()
cum = np.cumsum(r)
dd = np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum]))
wins = r[r > 0].sum()
losses = -r[r < 0].sum()
streak = best = 0
for x in r:
    streak = streak + 1 if x < 0 else 0
    best = max(best, streak)

print(f"trades {len(r)}  from {df.entry_time.min():%Y-%m-%d} to {df.exit_time.max():%Y-%m-%d}   cost/trade {cost_r}R")
print(f"total {cum[-1]:+.1f}R   avg {r.mean():+.3f}R   win {np.mean(r > 0):.0%}   PF(R) {wins / losses:.2f}   maxDD {dd:.1f}R   longest losing streak {best}")
print(f"avg win {r[r > 0].mean():+.2f}R  avg loss {r[r < 0].mean():+.2f}R  largest {r.max():+.1f}R")
m = df.groupby("month")["r"].agg(["count", "sum"])
print("monthly R: " + "  ".join(f"{k}: {v['sum']:+.1f} ({int(v['count'])})" for k, v in m.iterrows()))
dayr = df.groupby("day")["r"].sum()
print(f"worst day {dayr.min():+.1f}R   trading days {len(dayr)}")
top = np.sort(r)[::-1]
print(f"top 5 trades {top[:5].round(1).tolist()}  -> total without them {cum[-1] - top[:5].sum():+.1f}R")
print()

# ---------------------------------------------------------------------------------
def challenge(trades, risk_fn, target=10.0, max_loss=10.0, daily=5.0, int_total=8.0, int_daily=4.0,
              horizon_days=30, min_days=4, start=None):
    """trades: list of (entry_ts, exit_ts, day, R). Returns (status, days, peak_dd)."""
    bal = 0.0          # % of initial balance
    day = None
    day_start = 0.0
    tdays = set()
    for et, xt, d, rr in trades:
        elapsed = (xt - start).total_seconds() / 86400
        if elapsed > horizon_days:
            break
        if d != day:
            day, day_start = d, bal
        risk = risk_fn(bal)
        day_loss = day_start - bal
        if -bal + risk > int_total:
            return "fail", elapsed      # stuck under the internal max loss limit: cannot continue
        if day_loss + risk > int_daily or risk <= 0:
            continue
        bal += rr * risk
        tdays.add(d)
        if day_start - bal >= daily or -bal >= max_loss:
            return "fail", elapsed
        if bal >= target and len(tdays) >= min_days:
            return "pass", elapsed
    return "open", horizon_days


def fixed(p):
    return lambda bal: p


def buffer_scaled(cap, n, floor=0.25, int_total=8.0):
    # Risk a 1/n share of what is left before the internal max loss limit, capped.
    return lambda bal: max(min(cap, (int_total + bal) / n), floor)


def target_scaled(cap, n, floor=0.25, target=10.0, int_total=8.0):
    # As buffer_scaled, but never risk more than needed to finish in ~3 winners at 2R.
    return lambda bal: max(min(cap, (int_total + bal) / n, max((target - bal) / 6, floor)), floor)


tr = list(df[["entry_time", "exit_time", "day", "r"]].itertuples(index=False, name=None))

# Start at every Prague midnight that has 30 full days of data behind it.
tz = "Europe/Prague"
first = df.entry_time.min().tz_convert(tz).normalize()
last = df.exit_time.max().tz_convert(tz).normalize()
starts = [first + pd.Timedelta(days=i) for i in range(0, (last - first).days - 29)]
starts = [s for s in starts if s.weekday() < 5]

schemes = {
    "fixed 0.50%": fixed(0.5),
    "fixed 0.75%": fixed(0.75),
    "fixed 1.00%": fixed(1.0),
    "fixed 1.25%": fixed(1.25),
    "fixed 1.50%": fixed(1.5),
    "fixed 2.00%": fixed(2.0),
    "buffer/8 cap 1.5%": buffer_scaled(1.5, 8),
    "buffer/6 cap 1.5%": buffer_scaled(1.5, 6),
    "buffer/6 cap 2.0%": buffer_scaled(2.0, 6),
    "buffer/7 cap 1.5%": buffer_scaled(1.5, 7),
    "buffer/8 cap 2.0%": buffer_scaled(2.0, 8),
    "buffer/10 cap 1.5%": buffer_scaled(1.5, 10),
    "buffer/5 cap 1.5%": buffer_scaled(1.5, 5),
    "target-aware cap 1.5% /6": target_scaled(1.5, 6),
}

print(f"HISTORICAL REPLAY - {len(starts)} start days (overlapping windows, ~{len(starts) / 21:.0f} independent months)")
print(f"{'scheme':28s} {'pass<=30d':>9s} {'pass<=60d':>9s} {'fail<=60d':>9s} {'median days':>11s}")
for name, fn in schemes.items():
    res30 = []
    res60 = []
    for s in starts:
        sub = [t for t in tr if t[0] >= s]
        res30.append(challenge(sub, fn, start=s, horizon_days=30))
        res60.append(challenge(sub, fn, start=s, horizon_days=60))
    p30 = np.mean([x[0] == "pass" for x in res30])
    p60 = np.mean([x[0] == "pass" for x in res60])
    f60 = np.mean([x[0] == "fail" for x in res60])
    med = np.median([x[1] for x in res60 if x[0] == "pass"]) if any(x[0] == "pass" for x in res60) else float("nan")
    print(f"{name:28s} {p30:9.0%} {p60:9.0%} {f60:9.0%} {med:11.0f}")

# ---------------------------------------------------------------------------------
# Day-block bootstrap: rebuild 30-day challenges from randomly drawn real trading days
# (keeps each day's trades together, so same-day loss clusters are preserved).
rng = np.random.default_rng(7)
days = sorted(df["day"].unique())
by_day = {d: df.loc[df.day == d, "r"].tolist() for d in days}
cal_days = (last - first).days + 1
day_prob = len(days) / (cal_days * 5 / 7)   # share of weekdays that had a closed trade
N = 20000
print()
print(f"BOOTSTRAP - {N} synthetic challenges, 22 trading days each (~30 calendar days), {day_prob:.0%} of days trade")
print(f"{'scheme':28s} {'pass<=30d':>9s} {'fail<=30d':>9s} {'median days':>11s}")
day_list = [by_day[d] for d in days]
for name, fn in schemes.items():
    passes = fails = 0
    dpass = []
    for _ in range(N):
        bal = 0.0
        tdays = 0
        status = None
        for td in range(22):
            if rng.random() > day_prob:
                continue
            rs = day_list[rng.integers(len(day_list))]
            day_start = bal
            traded = False
            for rr in rs:
                risk = fn(bal)
                if -bal + risk > 8.0:
                    status = "fail"
                    break
                if (day_start - bal) + risk > 4.0 or risk <= 0:
                    continue
                bal += rr * risk
                traded = True
                if day_start - bal >= 5.0 or -bal >= 10.0:
                    status = "fail"
                    break
            tdays += traded
            if status:
                break
            if bal >= 10.0 and tdays >= 4:
                status = "pass"
                dpass.append(td + 1)
                break
        passes += status == "pass"
        fails += status == "fail"
    med = np.median(dpass) * 7 / 5 if dpass else float("nan")
    print(f"{name:28s} {passes / N:9.0%} {fails / N:9.0%} {med:11.0f}")

