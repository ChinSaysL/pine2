"""Generic single-position event engine for concept research (results in R after costs).

gen(i) is called at the close of bar i when flat and entries are allowed; it returns None or a list of
orders (one-cancels-other).  Order keys:
  kind       "mkt" (fills at the next bar's open) or "stop" (trigger price)
  dir        +1 / -1
  trigger    stop-entry price (kind "stop")
  valid      bars the order stays live (default 1)
  stop       absolute stop price, or stop_dist (distance from the fill)
  target     absolute target price, or tgt_r (multiple of the fill's risk), or None
  hold       close after this many bars in the trade
  exit_at    close at the end of the bar that ends at this NY hour (e.g. 7.0)
  exit_fn    callable(i, pos) -> True to close at bar i's close
  trail      trail the stop this many ATR behind the best price
  swing      True: hold overnight, flat only before the weekend (Friday 16:50 NY)
Conservative intrabar rules: stop before target; if a fill bar also touches the stop, it is stopped.
"""
import numpy as np
import pandas as pd

COST_OZ = 0.30
SLIP_MKT = 0.02    # ATR
SLIP_STOP = 0.05   # ATR


def daily_frame(df):
    d = df.groupby("tday").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    d["rng"] = d.h - d.l
    d["wd"] = [pd.Timestamp(x).weekday() for x in d.index]
    return d


def run(df, gen, allowed=None, cost=COST_OZ, flat_ny=16 + 50 / 60, last_entry_ny=None, swing_entries=False):
    o, h, l, c, atr = df.o.values, df.h.values, df.l.values, df.c.values, df.atr.values
    ny_h = df.ny_h.values
    tf = df.tf_h.values[0]
    wd = df.time.dt.tz_convert("America/New_York").dt.weekday.values
    end_h = (ny_h + tf) % 24
    closing = (ny_h + tf > flat_ny) & (ny_h < 18.0) & (ny_h >= 12.0)
    next_closing = np.roll(closing, -1)
    fri_close = closing & (wd == 4)
    n = len(df)
    if allowed is None:
        allowed = np.ones(n, bool)
    trades = []
    pos = None
    pend = []

    def close(i, px, why):
        nonlocal pos
        trades.append(dict(entry_time=df.time.iloc[pos["i"]], exit_time=df.time.iloc[i], dir=pos["dir"],
                           r=((px - pos["entry"]) * pos["dir"] - cost) / pos["risk"], why=why, bars=i - pos["i"] + 1,
                           entry=pos["entry"], risk=pos["risk"]))
        pos = None

    def open_pos(od, i, fill):
        nonlocal pos
        d = od["dir"]
        stop = od["stop"] if "stop" in od else fill - d * od["stop_dist"]
        risk = (fill - stop) * d
        if risk <= 0:
            return
        tgt = od.get("target")
        if tgt is None and od.get("tgt_r"):
            tgt = fill + d * od["tgt_r"] * risk
        if tgt is not None and (tgt - fill) * d <= 0:
            return
        pos = dict(od, dir=d, entry=fill, stop=stop, target=tgt, risk=risk, i=i, best=fill)

    for i in range(1, n):
        # ---- fills -------------------------------------------------------------------------------
        if pos is None and pend:
            hit = []
            for od in pend:
                if od["kind"] == "mkt":
                    hit.append((od, o[i] + od["dir"] * SLIP_MKT * atr[i]))
                elif (od["dir"] == 1 and h[i] >= od["trigger"]) or (od["dir"] == -1 and l[i] <= od["trigger"]):
                    px = max(o[i], od["trigger"]) if od["dir"] == 1 else min(o[i], od["trigger"])
                    hit.append((od, px + od["dir"] * SLIP_STOP * atr[i]))
            if len(hit) == 1:
                open_pos(hit[0][0], i, hit[0][1])
                pend = []
                if pos is not None and ((pos["dir"] == 1 and l[i] <= pos["stop"]) or (pos["dir"] == -1 and h[i] >= pos["stop"])):
                    close(i, pos["stop"], "stop")
                    continue
                if pos is not None:
                    pos["best"] = max(pos["best"], h[i]) if pos["dir"] == 1 else min(pos["best"], l[i])
            elif len(hit) > 1:
                pend = []
            else:
                pend = [od for od in pend if od["kind"] == "stop" and i + 1 < od["exp"]]
        # ---- manage ------------------------------------------------------------------------------
        elif pos is not None:
            d = pos["dir"]
            if (d == 1 and l[i] <= pos["stop"]) or (d == -1 and h[i] >= pos["stop"]):
                close(i, min(o[i], pos["stop"]) if d == 1 else max(o[i], pos["stop"]), "stop")
            elif pos["target"] is not None and ((d == 1 and h[i] >= pos["target"]) or (d == -1 and l[i] <= pos["target"])):
                close(i, max(o[i], pos["target"]) if d == 1 else min(o[i], pos["target"]), "target")
            else:
                pos["best"] = max(pos["best"], h[i]) if d == 1 else min(pos["best"], l[i])
                if pos.get("trail"):
                    ns = pos["best"] - d * pos["trail"] * atr[i]
                    pos["stop"] = max(pos["stop"], ns) if d == 1 else min(pos["stop"], ns)
        if pos is not None:
            why = None
            if (fri_close[i] if pos.get("swing") else closing[i]):
                why = "flat"
            elif pos.get("exit_at") is not None and abs(end_h[i] - pos["exit_at"]) < 1e-6:
                why = "time"
            elif pos.get("hold") and i - pos["i"] + 1 >= pos["hold"]:
                why = "hold"
            elif pos.get("exit_fn") is not None and pos["exit_fn"](i, pos):
                why = "rule"
            if why:
                close(i, c[i], why)
        # ---- new signals -------------------------------------------------------------------------
        if pos is None and allowed[i] and (swing_entries or (not closing[i] and not next_closing[i])) and \
                (last_entry_ny is None or not (last_entry_ny <= ny_h[i] < 18.0)):
            ods = gen(i)
            if ods:
                for od in ods:
                    od.setdefault("kind", "mkt")
                    od["exp"] = i + 1 + od.get("valid", 1)
                pend = ods
    return pd.DataFrame(trades)
