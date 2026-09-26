"""Bar-by-bar replay of the strategy part of pinescsript.txt.

It follows the Pine script's order of operations on every bar and TradingView's broker
emulator rules (process_orders_on_close, limit/stop fills inside the bar, whole-unit
order sizes), so that on the same price data it should reproduce the Strategy Tester's
List of trades. Settings mirror the script's defaults.
"""
import math
import numpy as np
import pandas as pd

from signals import compute

NY, PRAGUE = "America/New_York", "Europe/Prague"

# Same list as the "News Events (New York time)" input.
NEWS_ET = (["2026-%s 08:30" % d for d in ["01-09", "01-13", "02-11", "02-13", "03-06", "03-11", "04-03", "04-10", "05-08", "05-12",
                                          "06-05", "06-10", "07-02", "07-14", "08-07", "08-12", "09-04", "09-11", "10-02", "10-14",
                                          "11-06", "11-10", "12-04", "12-10"]]
           + ["2026-%s 14:00" % d for d in ["01-28", "02-18", "03-18", "04-08", "04-29", "05-20", "06-17", "07-08", "07-29", "08-19",
                                            "09-16", "10-28", "12-09"]])

DEFAULTS = dict(capital=10000.0, riskPct=0.5, maxStopAtr=1.5, pullAtr=0.25, pullBars=4, tpMinR=2.0,
                volFilter=True, volMin=30, volMax=70, dailyLimit=4.0, totalLimit=8.0,
                newsBefore=20, newsAfter=15, flatBeforeClose=True, newsFilter=True, pointValue=1.0)


def rma_pine(x, n):
    """ta.rma: seeded with the SMA of the first n values."""
    out = np.full(len(x), np.nan); s = None; buf = []
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        if s is None:
            buf.append(v)
            if len(buf) == n:
                s = float(np.mean(buf)); out[i] = s
        else:
            s = (s * (n - 1) + v) / n; out[i] = s
    return out


def percentrank_pine(x, n):
    """ta.percentrank: share of the previous n values that are <= the current one."""
    s = pd.Series(x)
    return s.rolling(n + 1).apply(lambda v: np.nan if np.isnan(v).any() else (v[:-1] <= v[-1]).mean() * 100, raw=True).values


def session_masks(index, p):
    close_t = index + pd.Timedelta("15min")                     # decisions happen at the bar close
    ny = close_t.tz_convert(NY); hm = ny.hour * 60 + ny.minute
    near_close = np.asarray((hm >= 16 * 60 + 45) & (hm < 18 * 60)) if p["flatBeforeClose"] else np.zeros(len(index), bool)
    near_news = np.zeros(len(index), bool)
    if p["newsFilter"]:
        for e in pd.to_datetime(NEWS_ET).tz_localize(NY).tz_convert("UTC"):
            d = (e - close_t).total_seconds() / 60
            near_news |= np.asarray((d <= p["newsBefore"]) & (d >= -p["newsAfter"]))
    prague_day = np.asarray(close_t.tz_convert(PRAGUE).day)
    return near_close, near_news, prague_day


def replay(df, **kw):
    p = dict(DEFAULTS); p.update(kw)
    S = compute(df, maxData=len(df))
    idx = S.index; n = len(S)
    o, h, l, c = S.o.values, S.h.values, S.l.values, S.c.values
    ts, atr, os_ = S.ts.values, S.atr.values, S.os.values
    buy, sell, bex, uex = S.buy.values, S.sell.values, S.bearEx.values, S.bullEx.values
    osp = np.r_[0, os_[:-1]]
    close_vol = rma_pine(np.abs(np.r_[np.nan, np.diff(c)]), 20)
    vol_pct = percentrank_pine(close_vol, 500)
    near_close, near_news, pday = session_masks(idx, p)
    pv = p["pointValue"]; cap = p["capital"]

    cash = cap; netprofit = 0.0
    pos = 0; qty = 0.0; entry_px = np.nan; stop_px = np.nan      # broker position and its stop order
    trade_dir = 0; trade_entry = np.nan; trade_risk = np.nan; trade_bar = -1
    pend = None                                                   # (dir, limit, stop, qty, bar)
    day_start_eq = cap
    trades = []; cur = None

    def open_pos(d, px, q, bar, stop):
        nonlocal pos, qty, entry_px, stop_px, cur
        pos, qty, entry_px, stop_px = d, q, px, stop
        cur = dict(entry_time=idx[bar], dir=d, entry=px, qty=q)

    def close_pos(px, bar, why):
        nonlocal pos, qty, cash, netprofit, cur
        pnl = (px - entry_px) * pos * qty * pv
        cash += pnl; netprofit += pnl
        cur.update(exit_time=idx[bar], exit=px, pnl=pnl, why=why); trades.append(cur); cur = None
        pos = 0; qty = 0.0

    for i in range(n):
        # ---- inside the bar: broker emulator ------------------------------------------
        if pend is not None and pos == 0:
            d, lim, stp, q, pb = pend
            if (d == 1 and l[i] <= lim) or (d == -1 and h[i] >= lim):
                fill = min(o[i], lim) if d == 1 else max(o[i], lim)
                open_pos(d, fill, q, i, stp)
                if (d == 1 and l[i] <= stp) or (d == -1 and h[i] >= stp):
                    close_pos(min(fill, stp) if d == 1 else max(fill, stp), i, "SL")
        elif pos != 0 and i > trade_bar and not np.isnan(stop_px):
            if (pos == 1 and l[i] <= stop_px) or (pos == -1 and h[i] >= stop_px):
                close_pos(min(o[i], stop_px) if pos == 1 else max(o[i], stop_px), i, "SL")

        # ---- at the bar close: the script -----------------------------------------------
        equity = cash + ((c[i] - entry_px) * pos * qty * pv if pos else 0.0)

        # pullback order filled inside the bar
        if pend is not None and pos == pend[0]:
            trade_dir, trade_entry, trade_risk, trade_bar = pend[0], entry_px, abs(entry_px - pend[2]), i
            pend = None
        if pend is not None and pos == 0 and trades and trades[-1]["entry_time"] > idx[pend[4]]:
            pend = None                                          # filled and stopped in the same bar
        if trade_dir != 0 and i > trade_bar and pos == 0:
            trade_dir = 0

        run_r = (c[i] - trade_entry) * trade_dir / trade_risk if trade_dir else 0.0
        tp_hit = trade_dir != 0 and i > trade_bar and (bex[i] if trade_dir == 1 else uex[i]) and run_r >= max(p["tpMinR"], 1e-4)
        flip = (os_[i] < osp[i]) if trade_dir == 1 else (os_[i] > osp[i]) if trade_dir == -1 else False

        stop_dist = abs(c[i] - ts[i])
        if p["maxStopAtr"] > 0: stop_dist = min(stop_dist, p["maxStopAtr"] * atr[i])
        if not stop_dist > 0: stop_dist = atr[i]
        if np.isnan(stop_dist):                                  # indicators still warming up
            continue
        risk_qty = max(math.floor(equity * p["riskPct"] / 100 / (stop_dist * pv)), 1)

        if i > 0 and pday[i] != pday[i - 1]:
            day_start_eq = max(equity, cap + netprofit)
        day_loss = (day_start_eq - equity) / cap * 100
        total_loss = (cap - equity) / cap * 100
        limit_hit = day_loss >= p["dailyLimit"] or total_loss >= p["totalLimit"]
        new_risk = risk_qty * stop_dist * pv / cap * 100
        risk_fits = day_loss + new_risk <= p["dailyLimit"] and total_loss + new_risk <= p["totalLimit"]
        vol_ok = (not p["volFilter"]) or np.isnan(vol_pct[i]) or (p["volMin"] <= vol_pct[i] < p["volMax"])
        can_enter = vol_ok and not near_news[i] and not near_close[i] and not limit_hit and risk_fits
        use_pull = p["pullAtr"] > 0 and stop_dist > (p["pullAtr"] + 0.5) * atr[i]

        reason = ("Loss Limit" if limit_hit else "TP Warning" if tp_hit else "News" if near_news[i]
                  else "Market Close" if near_close[i] else "Signal Flip" if flip else "")
        if trade_dir != 0 and reason:
            reversing = (sell[i] if trade_dir == 1 else buy[i]) and can_enter and not use_pull
            if pos:
                close_pos(c[i], i, "Signal Flip" if reversing else reason)
            trade_dir = 0

        if pend is not None and (i >= pend[4] + p["pullBars"] or near_news[i] or near_close[i] or limit_hit
                                 or (sell[i] if pend[0] == 1 else buy[i])):
            pend = None

        for d, sig in ((1, buy[i]), (-1, sell[i])):
            if sig and trade_dir != d and can_enter:
                stp = c[i] - d * stop_dist
                if use_pull:
                    lim = c[i] - d * p["pullAtr"] * atr[i]
                    q = max(math.floor(equity * p["riskPct"] / 100 / (abs(lim - stp) * pv)), 1)
                    pend = (d, lim, stp, q, i)
                else:
                    if pos:                                          # market reversal
                        close_pos(c[i], i, "Signal Flip")
                    open_pos(d, c[i], risk_qty, i, stp)
                    trade_dir, trade_entry, trade_risk, trade_bar = d, c[i], stop_dist, i

    T = pd.DataFrame(trades)
    return T, S
