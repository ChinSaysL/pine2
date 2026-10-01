"""Breakout with pyramiding: add a unit at +1R (and optionally +2R) of the first unit; on each add the
whole position's stop moves to at least the first entry (breakeven). Every unit is recorded as its own
trade with its own R, so the FTMO simulator counts the open risk of every unit (conservative: it keeps
counting the first unit's full risk even after its stop reached breakeven)."""
import numpy as np
import pandas as pd

from concepts import COST_OZ, SLIP_ATR


def simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=None, add_at=(1.0,), flat_ny=16.75, move_be=True,
                 fail_exit_bars=0, fail_exit_buf=0.0):
    """fail_exit_bars: exit at the close of any of the first N bars (the breakout bar = 1) that closes back
    inside the channel, i.e. beyond the breakout level by more than fail_exit_buf ATR. 0 = off."""
    o, h, l, c, atr = df.o.values, df.h.values, df.l.values, df.c.values, df.atr.values
    ny_h = df.ny_h.values
    tf_h = df.tf_h.values[0]
    n = max(int(round(hours / tf_h)), 2)
    hh = pd.Series(h).rolling(n).max().values
    ll = pd.Series(l).rolling(n).min().values
    trades = []
    pos = None
    orders = []

    def close_all(i, px, why):
        nonlocal pos
        for u in pos["units"]:
            r = ((px - u["entry"]) * pos["dir"] - COST_OZ) / u["risk"]
            trades.append(dict(entry_time=df.time.iloc[u["i"]], exit_time=df.time.iloc[i], dir=pos["dir"],
                               unit=u["k"], r=r, why=why, entry=u["entry"], risk=u["risk"], entry_i=u["i"], exit_i=i,
                               mfe_r=(pos["best"] - pos["units"][0]["entry"]) * pos["dir"] / pos["units"][0]["risk"],
                               level=pos.get("level")))
        pos = None

    for i in range(1, len(df)):
        closing = (ny_h[i] + tf_h > flat_ny) and ny_h[i] < 18.0 and ny_h[i] >= 12.0
        if pos is not None:
            d = pos["dir"]
            if (d == 1 and l[i] <= pos["stop"]) or (d == -1 and h[i] >= pos["stop"]):
                close_all(i, min(o[i], pos["stop"]) if d == 1 else max(o[i], pos["stop"]), "stop")
        if pos is not None:
            pos["best"] = max(pos["best"], h[i]) if pos["dir"] == 1 else min(pos["best"], l[i])
        if pos is not None and i > pos["units"][0]["i"]:
            d = pos["dir"]
            u0 = pos["units"][0]
            k = len(pos["units"])
            if k <= len(add_at) and not closing:
                lvl = u0["entry"] + d * add_at[k - 1] * u0["risk"]
                if (d == 1 and h[i] >= lvl) or (d == -1 and l[i] <= lvl):
                    fill = (max(o[i], lvl) + SLIP_ATR * atr[i]) if d == 1 else (min(o[i], lvl) - SLIP_ATR * atr[i])
                    if move_be:
                        pos["stop"] = max(pos["stop"], u0["entry"]) if d == 1 else min(pos["stop"], u0["entry"])
                    risk = abs(fill - pos["stop"])
                    if risk > 0.1 * atr[i]:
                        pos["units"].append(dict(k=k, entry=fill, risk=risk, i=i))
        if pos is not None and fail_exit_bars > 0 and i - pos["units"][0]["i"] < fail_exit_bars and i > pos["units"][0]["i"]:
            d = pos["dir"]
            if (d == 1 and c[i] < pos["level"] - fail_exit_buf * atr[i]) or (d == -1 and c[i] > pos["level"] + fail_exit_buf * atr[i]):
                close_all(i, c[i], "failed breakout")
        if pos is not None and closing:
            close_all(i, c[i], "time")
        if pos is not None:
            d = pos["dir"]
            seg = h[pos["units"][0]["i"]:i + 1].max() if d == 1 else l[pos["units"][0]["i"]:i + 1].min()
            ns = seg - trail_atr * atr[i] if d == 1 else seg + trail_atr * atr[i]
            if i > pos["units"][0]["i"]:
                pos["stop"] = max(pos["stop"], ns) if d == 1 else min(pos["stop"], ns)
        if pos is None and not closing:
            for od in orders:
                d, trig = od["dir"], od["trigger"]
                if (d == 1 and h[i] >= trig) or (d == -1 and l[i] <= trig):
                    fill = (max(o[i], trig) + SLIP_ATR * atr[i]) if d == 1 else (min(o[i], trig) - SLIP_ATR * atr[i])
                    risk = abs(fill - od["stop"])
                    if risk <= 0:
                        continue
                    pos = dict(dir=d, stop=od["stop"], units=[dict(k=0, entry=fill, risk=risk, i=i)],
                               best=c[i], level=trig)
                    if (d == 1 and c[i] <= od["stop"]) or (d == -1 and c[i] >= od["stop"]):
                        close_all(i, od["stop"], "stop")
                    elif fail_exit_bars > 0 and ((d == 1 and c[i] < trig - fail_exit_buf * atr[i]) or (d == -1 and c[i] > trig + fail_exit_buf * atr[i])):
                        close_all(i, c[i], "failed breakout")
                    break
        orders = []
        if not closing and i >= n and not np.isnan(atr[i]):
            a = atr[i]
            if trend is None or trend[i] == 1:
                t = hh[i] + 0.05 * a
                orders.append(dict(dir=1, trigger=t, stop=t - stop_atr * a))
            if trend is None or trend[i] == -1:
                t = ll[i] - 0.05 * a
                orders.append(dict(dir=-1, trigger=t, stop=t + stop_atr * a))
    return pd.DataFrame(trades)
