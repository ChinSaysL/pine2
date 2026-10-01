"""Range / mean-reversion concepts for the BAD regime (pre-registered, H1, results in R after $0.30/oz).

Signals are computed on bar i's close; entry at bar i+1's open. Stop checked before target inside a bar.
Flat before 16:50 NY like the trend EA; no entries on the closing bar or the one before it.
"""
import numpy as np
import pandas as pd

COST_OZ = 0.30


def run(df, signal_fn, flat_ny=16 + 50 / 60, allowed=None):
    """signal_fn(i) -> None or dict(dir, stop, target) using data up to bar i's close.
    allowed: optional bool array per bar - entry only if allowed[i] (e.g. BAD regime)."""
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    ny_h = df.ny_h.values
    tf_h = df.tf_h.values[0]
    closing = (ny_h + tf_h > flat_ny) & (ny_h < 18.0) & (ny_h >= 12.0)
    next_closing = np.roll(closing, -1)
    trades, pos, pend = [], None, None
    for i in range(1, len(df)):
        if pend is not None and pos is None:
            d, entry = pend["dir"], o[i]
            risk = (entry - pend["stop"]) * d
            if risk > 0 and (pend["target"] - entry) * d > 0:
                pos = dict(pend, entry=entry, risk=risk, i=i)
        pend = None
        if pos is not None:
            d = pos["dir"]
            px = why = None
            if (d == 1 and l[i] <= pos["stop"]) or (d == -1 and h[i] >= pos["stop"]):
                px, why = (min(o[i], pos["stop"]) if d == 1 else max(o[i], pos["stop"])), "stop"
            elif (d == 1 and h[i] >= pos["target"]) or (d == -1 and l[i] <= pos["target"]):
                px, why = (max(o[i], pos["target"]) if d == 1 else min(o[i], pos["target"])), "target"
            elif closing[i]:
                px, why = c[i], "time"
            if px is not None:
                trades.append(dict(entry_time=df.time.iloc[pos["i"]], exit_time=df.time.iloc[i], dir=d,
                                   r=((px - pos["entry"]) * d - COST_OZ) / pos["risk"], why=why))
                pos = None
        if pos is None and not closing[i] and not next_closing[i] and (allowed is None or allowed[i]):
            s = signal_fn(i)
            if s is not None:
                pend = s
    return pd.DataFrame(trades)


def c1_failed_breakout(df, hours=24, stop_buf=0.25, target="mid", tgt_r=1.5):
    """Bar pokes above the prior `hours` high (or below the low) and closes back inside -> fade it."""
    h, l, c, atr = df.h.values, df.l.values, df.c.values, df.atr.values
    hh = pd.Series(h).rolling(hours).max().shift(1).values
    ll = pd.Series(l).rolling(hours).min().shift(1).values

    def sig(i):
        if np.isnan(hh[i]) or np.isnan(atr[i]):
            return None
        mid = (hh[i] + ll[i]) / 2
        if h[i] > hh[i] and c[i] < hh[i]:
            stop = h[i] + stop_buf * atr[i]
            tgt = mid if target == "mid" else c[i] - tgt_r * (stop - c[i])
            return dict(dir=-1, stop=stop, target=tgt)
        if l[i] < ll[i] and c[i] > ll[i]:
            stop = l[i] - stop_buf * atr[i]
            tgt = mid if target == "mid" else c[i] + tgt_r * (c[i] - stop)
            return dict(dir=1, stop=stop, target=tgt)
        return None
    return sig


def c2_stretch_fade(df, hours=24, k=2.0, stop_atr=1.5):
    """Close more than k ATR away from the `hours` average -> fade it back to the average."""
    c, atr = df.c.values, df.atr.values
    ma = pd.Series(c).rolling(hours).mean().values

    def sig(i):
        if np.isnan(ma[i]) or np.isnan(atr[i]):
            return None
        if c[i] > ma[i] + k * atr[i]:
            return dict(dir=-1, stop=c[i] + stop_atr * atr[i], target=ma[i])
        if c[i] < ma[i] - k * atr[i]:
            return dict(dir=1, stop=c[i] - stop_atr * atr[i], target=ma[i])
        return None
    return sig


PERIODS = [("dev 20-01..22-06", "2020-01-01", "2022-07-01"),
           ("holdA 22-07..24-06", "2022-07-01", "2024-07-01"),
           ("holdB 24-07..26-09", "2024-07-01", "2026-10-01")]


def summary(t, label):
    out = {"concept": label}
    for name, a, b in PERIODS:
        s = t[(t.entry_time >= a) & (t.entry_time < b)]
        pf = s.r[s.r > 0].sum() / max(-s.r[s.r < 0].sum(), 1e-9)
        out[name] = f"{s.r.sum():+6.1f}R n={len(s):4d} PF={pf:4.2f}"
    return out
