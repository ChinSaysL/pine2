"""Python replica of the strategy's trade logic on dumped TradingView bars.

Bars come from the RESEARCH DUMP (one row per bar):
  time_min, o, h, l, c, atr, ts, os, pass, volOk, blocked(news/close), bearEx, bullEx, cond, perf
Results are in R (1R = entry to initial stop) with costs ($/oz round trip) converted to R.
"""
import numpy as np
import pandas as pd

COLS = ["tmin", "o", "h", "l", "c", "atr", "ts", "os", "pas", "volok", "blocked", "bearex", "bullex", "cond", "perf"]


def load(path):
    t = open(path).read().split("\n")[1:]
    rows = [r.split(",") for c in t for r in c.split(";") if r]
    df = pd.DataFrame(rows, columns=COLS)
    for k in COLS:
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df["time"] = pd.to_datetime(df.tmin * 60, unit="s", utc=True)
    ny = df.time.dt.tz_convert("America/New_York")
    nymin = ny.dt.hour * 60 + ny.dt.minute
    df["usopen"] = (nymin >= 8 * 60) & (nymin < 13 * 60)          # bar opens inside 08:00-13:00 NY
    df["prague_day"] = df.time.dt.tz_convert("Europe/Prague").dt.date
    return df.reset_index(drop=True)


DEFAULT = dict(
    max_stop_atr=1.5, pull_atr=0.25, pull_bars=4, tp_min_r=2.0,
    lock_start=1.5, lock_giveback=0.40, cost_per_oz=0.30,
    skip_usopen=True, exit_on_filtered_flip=True,
    # --- logic extensions (off by default) ---
    chop_flips=0, chop_window=0,          # skip if the trailing line flipped >= chop_flips times in chop_window bars
    entry_mode="flip",                    # "flip" = current; "retest" = wait for a pullback to the trailing line
    retest_bars=12, retest_buffer_atr=0.2,
    trail_line_after_r=0.0,               # >0: after this many R, trail the stop on the trailing line (ts)
    confirm_bars=3, confirm_buffer_atr=0.05,  # entry_mode "confirm": stop order beyond the signal bar, valid N bars
    er_hours=0.0, er_min=0.0,             # efficiency ratio regime filter over this many hours (0 = off)
    # entry_mode "pullback": the flip only sets the direction; while that trend lasts, enter
    # on any bar that dips to within pb_touch_atr of the line and closes back beyond it.
    pb_touch_atr=0.3, pb_stop_atr=0.2, pb_max_bars=0, pb_need_filter=True, pb_max_entries=0,
    signal_filter=None,                   # callable(df, i, dir) -> bool, extra entry condition
)


def run(df, **kw):
    p = dict(DEFAULT, **kw)
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    atr, ts, os_ = df.atr.values, df.ts.values, df.os.values
    pas, volok, blocked = df.pas.values == 1, df.volok.values == 1, df.blocked.values == 1
    bearex, bullex = df.bearex.values == 1, df.bullex.values == 1
    usopen = df.usopen.values
    n = len(df)

    flips = np.zeros(n)
    flips[1:] = np.where(os_[1:] != os_[:-1], 1, 0)
    flip_count = pd.Series(flips).rolling(max(p["chop_window"], 1), min_periods=1).sum().values

    er = None
    if p["er_hours"] > 0:
        tf_min = float(np.median(np.diff(df.tmin.values[:200])))
        nbar = max(int(round(p["er_hours"] * 60 / tf_min)), 2)
        cs = pd.Series(c)
        er = (cs.diff(nbar).abs() / cs.diff().abs().rolling(nbar).sum()).values

    trades = []
    pos = None          # dict(dir, entry, stop, risk, bar, best, stop_oz)
    conf = None         # dict(dir, trigger, bar) stop entry waiting for confirmation
    pb_state = {}       # pullback mode: current trend leg
    pend = None         # dict(dir, limit, stop, bar)
    retest = None       # dict(dir, bar, line) waiting for a retest of the trailing line

    def close_trade(i, price, reason):
        nonlocal pos
        r = (price - pos["entry"]) * pos["dir"] / pos["risk"] - p["cost_per_oz"] / pos["risk"]
        trades.append(dict(entry_i=pos["bar"], exit_i=i, dir=pos["dir"], entry=pos["entry"], exit=price,
                           stop_oz=pos["risk"], r=r, reason=reason))
        pos = None

    for i in range(1, n):
        if np.isnan(atr[i]) or np.isnan(ts[i]):
            continue
        # ---- intrabar: pending limit fill, then stop -------------------------------------------
        if pend is not None and i > pend["bar"]:
            d = pend["dir"]
            hit = l[i] <= pend["limit"] if d == 1 else h[i] >= pend["limit"]
            if hit:
                fill = min(o[i], pend["limit"]) if d == 1 else max(o[i], pend["limit"])
                pos = dict(dir=d, entry=fill, stop=pend["stop"], risk=abs(fill - pend["stop"]), bar=i, best=c[i], ext=np.nan)
                pend = None
                # conservative: a stop inside the fill bar counts
                if (d == 1 and l[i] <= pos["stop"]) or (d == -1 and h[i] >= pos["stop"]):
                    if (d == 1 and c[i] < fill) or (d == -1 and c[i] > fill):
                        close_trade(i, pos["stop"], "SL")
        if conf is not None and pos is None and i > conf["bar"]:
            d = conf["dir"]
            if (d == 1 and h[i] >= conf["trigger"]) or (d == -1 and l[i] <= conf["trigger"]):
                fill = max(o[i], conf["trigger"]) if d == 1 else min(o[i], conf["trigger"])
                dist = min(abs(fill - ts[conf["bar"]]), p["max_stop_atr"] * atr[conf["bar"]])
                dist = dist if dist > 0 else atr[conf["bar"]]
                pos = dict(dir=d, entry=fill, stop=fill - d * dist, risk=dist, bar=i, best=c[i], ext=np.nan)
                conf = None
                if (d == 1 and c[i] <= pos["stop"]) or (d == -1 and c[i] >= pos["stop"]):
                    close_trade(i, pos["stop"], "SL")
        if pos is not None and i > pos["bar"]:
            d = pos["dir"]
            if (d == 1 and l[i] <= pos["stop"]) or (d == -1 and h[i] >= pos["stop"]):
                px = min(o[i], pos["stop"]) if d == 1 else max(o[i], pos["stop"])
                close_trade(i, px, "SL" if (px - pos["entry"]) * d < 0 else "Lock/Trail")

        # ---- bar close logic --------------------------------------------------------------------
        buy_raw = os_[i] > os_[i - 1]
        sell_raw = os_[i] < os_[i - 1]
        buy = buy_raw and pas[i]
        sell = sell_raw and pas[i]
        can_enter = volok[i] and not blocked[i] and not (p["skip_usopen"] and usopen[i])
        if p["chop_flips"] > 0 and flip_count[i] >= p["chop_flips"]:
            can_enter = False
        if er is not None and not (er[i] >= p["er_min"]):
            can_enter = False

        if pos is not None:
            d = pos["dir"]
            pos["best"] = max(pos["best"], c[i]) if d == 1 else min(pos["best"], c[i])
            run_r = (c[i] - pos["entry"]) * d / pos["risk"]
            best_r = (pos["best"] - pos["entry"]) * d / pos["risk"]
            tp_warn = i > pos["bar"] and (bearex[i] if d == 1 else bullex[i]) and run_r >= p["tp_min_r"]
            lock = p["lock_start"] > 0 and i > pos["bar"] and best_r >= p["lock_start"] and run_r <= best_r * (1 - p["lock_giveback"])
            flip_against = (sell or (p["exit_on_filtered_flip"] and sell_raw)) if d == 1 else (buy or (p["exit_on_filtered_flip"] and buy_raw))
            reason = "TP Warning" if tp_warn else "Blocked" if blocked[i] else "Profit Lock" if lock else "Signal Flip" if flip_against else ""
            if reason:
                close_trade(i, c[i], reason)
            elif p["trail_line_after_r"] > 0 and best_r >= p["trail_line_after_r"]:
                # trail on the trailing line while it sits on the right side of the stop
                if d == 1 and os_[i] == 1 and ts[i] > pos["stop"]:
                    pos["stop"] = ts[i]
                if d == -1 and os_[i] == 0 and ts[i] < pos["stop"]:
                    pos["stop"] = ts[i]

        if pend is not None:
            d = pend["dir"]
            if i >= pend["bar"] + p["pull_bars"] or blocked[i] or (sell_raw if d == 1 else buy_raw):
                pend = None
        if conf is not None:
            d = conf["dir"]
            if i >= conf["bar"] + p["confirm_bars"] or blocked[i] or (sell_raw if d == 1 else buy_raw):
                conf = None

        # ---- entries ---------------------------------------------------------------------------
        for d, sig in ((1, buy), (-1, sell)):
            if not sig or p["entry_mode"] == "pullback":
                continue
            if pos is not None and pos["dir"] == d:
                continue
            if p["signal_filter"] is not None and not p["signal_filter"](df, i, d):
                continue
            if not can_enter:
                continue
            if p["entry_mode"] == "retest":
                retest = dict(dir=d, bar=i)
                continue
            if p["entry_mode"] == "confirm":
                if pos is not None:
                    close_trade(i, c[i], "Signal Flip")
                pend = None
                conf = dict(dir=d, bar=i, trigger=(h[i] + p["confirm_buffer_atr"] * atr[i]) if d == 1 else (l[i] - p["confirm_buffer_atr"] * atr[i]))
                continue
            dist = min(abs(c[i] - ts[i]), p["max_stop_atr"] * atr[i]) if p["max_stop_atr"] > 0 else abs(c[i] - ts[i])
            if not dist > 0:
                dist = atr[i]
            use_pull = p["pull_atr"] > 0 and dist > (p["pull_atr"] + 0.5) * atr[i]
            if pos is not None:
                close_trade(i, c[i], "Signal Flip")
            if use_pull:
                pend = dict(dir=d, limit=c[i] - d * p["pull_atr"] * atr[i], stop=c[i] - d * dist, bar=i)
            else:
                pos = dict(dir=d, entry=c[i], stop=c[i] - d * dist, risk=dist, bar=i, best=c[i], ext=np.nan)

        # ---- pullback entry mode: trade pullbacks to the line for as long as the trend lasts -----
        if p["entry_mode"] in ("pullback", "both"):
            if buy_raw or sell_raw:
                trend = dict(dir=1 if buy_raw else -1, bar=i, ok=pas[i] or not p["pb_need_filter"], entries=0)
                pb_state["trend"] = trend
            trend = pb_state.get("trend")
            if trend is not None and pos is None and pend is None and trend["ok"] and i > trend["bar"] and can_enter:
                d = trend["dir"]
                fresh = p["pb_max_bars"] <= 0 or i - trend["bar"] <= p["pb_max_bars"]
                room = p["pb_max_entries"] <= 0 or trend["entries"] < p["pb_max_entries"]
                if fresh and room and (p["signal_filter"] is None or p["signal_filter"](df, i, d)):
                    touched = l[i] <= ts[i] + p["pb_touch_atr"] * atr[i] if d == 1 else h[i] >= ts[i] - p["pb_touch_atr"] * atr[i]
                    held = (c[i] > ts[i] and c[i] > o[i]) if d == 1 else (c[i] < ts[i] and c[i] < o[i])
                    if touched and held:
                        stop = min(l[i], ts[i]) - p["pb_stop_atr"] * atr[i] if d == 1 else max(h[i], ts[i]) + p["pb_stop_atr"] * atr[i]
                        dist = abs(c[i] - stop)
                        if 0 < dist <= p["max_stop_atr"] * atr[i] * 2:
                            pos = dict(dir=d, entry=c[i], stop=stop, risk=dist, bar=i, best=c[i], ext=np.nan)
                            trend["entries"] += 1

        # ---- retest entry mode: after a signal, buy the first pullback that holds the line -----
        if retest is not None and pos is None and pend is None:
            d = retest["dir"]
            if (d == 1 and os_[i] != 1) or (d == -1 and os_[i] != 0) or i > retest["bar"] + p["retest_bars"]:
                retest = None
            elif i > retest["bar"] and can_enter:
                touched = l[i] <= ts[i] + p["retest_buffer_atr"] * atr[i] if d == 1 else h[i] >= ts[i] - p["retest_buffer_atr"] * atr[i]
                held = c[i] > ts[i] and c[i] > o[i] if d == 1 else c[i] < ts[i] and c[i] < o[i]
                if touched and held:
                    stop = min(l[i], ts[i]) - 0.1 * atr[i] if d == 1 else max(h[i], ts[i]) + 0.1 * atr[i]
                    dist = abs(c[i] - stop)
                    if dist > 0:
                        pos = dict(dir=d, entry=c[i], stop=stop, risk=dist, bar=i, best=c[i], ext=np.nan)
                    retest = None

    t = pd.DataFrame(trades)
    if len(t):
        idx = pd.DatetimeIndex(df.time)
        t["entry_time"] = idx[t.entry_i.values]
        t["exit_time"] = idx[t.exit_i.values]
    return t


def stats(t, label=""):
    r = t.r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    dd = np.max(np.maximum.accumulate(cum) - cum)
    et = pd.to_datetime(t.entry_time)
    et = et.dt.tz_localize("UTC") if et.dt.tz is None else et
    s = lambda a, b: t.r[(et >= pd.Timestamp(a, tz="UTC")) & (et < pd.Timestamp(b, tz="UTC"))].sum()
    m = t.groupby(et.dt.strftime("%Y-%m")).r.sum()
    pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
    return dict(label=label, n=len(r), total=round(r.sum(), 1), pf=round(pf, 2), dd=round(dd, 1),
                h1=round(s("2026-04-01", "2026-07-01"), 1), h2=round(s("2026-07-01", "2026-10-01"), 1),
                mayjul=round(s("2026-05-01", "2026-08-01"), 1), aug19sep8=round(s("2026-08-19", "2026-09-08"), 1),
                win=round((r > 0).mean(), 2), months_pos=f"{(m > 0).sum()}/{len(m)}")
