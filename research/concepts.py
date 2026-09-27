"""New signal concepts for gold, researched with a fixed protocol.

Development: 2025 (30m and 1H).  Holdout: Jan - Sep 2026 (30m, 1H) and Apr - Sep 2026 (15m).
Results in R after costs. Intrabar ambiguity is resolved against us (stop before target).
"""
import numpy as np
import pandas as pd
from engine import load

COST_OZ = 0.30        # spread + commission, round trip, $/oz
SLIP_ATR = 0.05       # extra slippage on stop-entry fills, in ATR


def prep(df):
    df = df[["time", "o", "h", "l", "c"]].copy().reset_index(drop=True)
    tr = np.maximum(df.h - df.l, np.maximum((df.h - df.c.shift()).abs(), (df.l - df.c.shift()).abs()))
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    lon = df.time.dt.tz_convert("Europe/London")
    ny = df.time.dt.tz_convert("America/New_York")
    df["lon_h"] = lon.dt.hour + lon.dt.minute / 60
    df["ny_h"] = ny.dt.hour + ny.dt.minute / 60
    # trading day = New York day rolled at 17:00 (gold's daily break)
    df["tday"] = (ny + pd.Timedelta(hours=7)).dt.date
    df["tf_h"] = float(np.median(np.diff(df.time.values[:500]).astype("timedelta64[m]").astype(float))) / 60
    return df


class Book:
    """One position at a time; stop-entry orders; stop / target / time exits."""

    def __init__(self):
        self.trades = []

    def record(self, df, i0, i1, d, entry, stop0, exit_px, why):
        risk = abs(entry - stop0)
        r = ((exit_px - entry) * d - COST_OZ) / risk
        self.trades.append(dict(entry_time=df.time.iloc[i0], exit_time=df.time.iloc[i1], dir=d, entry=entry,
                                stop=stop0, exit=exit_px, risk=risk, r=r, why=why, exit_i=i1))


def daily_trend(df, n=50):
    """+1 / -1 per bar: previous trading day's close above / below its n-day average (no lookahead)."""
    closes = df.groupby("tday").c.last()
    sma = closes.rolling(n).mean()
    trend = np.sign(closes - sma).shift(1)          # known at the start of the next day
    return df.tday.map(trend).fillna(0).values


def simulate(df, orders_fn, manage_fn=None, flat_ny=16.75, target_r=2.0, max_hold_bars=None, allow_overnight=False,
             trend=None, last_entry_ny=None, max_losses_day=None, be_r=None):
    """orders_fn(df, i, state) -> list of dict(dir, trigger, stop) stop-entry orders valid this bar (or None).
    manage_fn(df, i, pos) -> new stop (trailing) or None.  trend: per-bar +1/-1 array; orders against it are dropped."""
    o, h, l, c, atr = df.o.values, df.h.values, df.l.values, df.c.values, df.atr.values
    ny_h, tday = df.ny_h.values, df.tday.values
    tf_h = df.tf_h.values[0]
    wd = df.time.dt.tz_convert("America/New_York").dt.weekday.values
    book = Book()
    pos = None
    state = {}
    for i in range(1, len(df)):
        # --- manage open position intrabar: stop first, then target -----------------------------
        if pos is not None:
            d = pos["dir"]
            if (d == 1 and l[i] <= pos["stop"]) or (d == -1 and h[i] >= pos["stop"]):
                px = min(o[i], pos["stop"]) if d == 1 else max(o[i], pos["stop"])
                book.record(df, pos["i"], i, d, pos["entry"], pos["stop0"], px, "stop")
                pos = None
            elif pos["target"] is not None and ((d == 1 and h[i] >= pos["target"]) or (d == -1 and l[i] <= pos["target"])):
                px = max(o[i], pos["target"]) if d == 1 else min(o[i], pos["target"])
                book.record(df, pos["i"], i, d, pos["entry"], pos["stop0"], px, "target")
                pos = None
        # --- flat before the daily close (or before the weekend when holding overnight) ----------
        # The last bar whose close is past flat_ny before the 17:00-18:00 break. (Testing the
        # bar's open time missed it on 30m / 1H, where no bar opens between 16:45 and 18:00.)
        closing = (ny_h[i] + tf_h > flat_ny) and ny_h[i] < 18.0 and ny_h[i] >= 12.0
        if allow_overnight:
            closing = closing and wd[i] == 4
        if pos is not None and (closing or (max_hold_bars and i - pos["i"] >= max_hold_bars)):
            book.record(df, pos["i"], i, pos["dir"], pos["entry"], pos["stop0"], c[i], "time")
            pos = None
        if pos is not None and manage_fn is not None:
            ns = manage_fn(df, i, pos)
            if ns is not None:
                pos["stop"] = max(pos["stop"], ns) if pos["dir"] == 1 else min(pos["stop"], ns)
        if pos is not None and be_r is not None and i > pos["i"]:
            risk0 = abs(pos["entry"] - pos["stop0"])
            best = (h[pos["i"]:i + 1].max() - pos["entry"]) if pos["dir"] == 1 else (pos["entry"] - l[pos["i"]:i + 1].min())
            if best >= be_r * risk0:
                pos["stop"] = max(pos["stop"], pos["entry"]) if pos["dir"] == 1 else min(pos["stop"], pos["entry"])
        # --- new entries: orders placed at bar i-1's close, fill inside bar i --------------------
        if pos is None and not closing:
            for od in state.get("orders", []) or []:
                d, trig = od["dir"], od["trigger"]
                if (d == 1 and h[i] >= trig) or (d == -1 and l[i] <= trig):
                    fill = (max(o[i], trig) + SLIP_ATR * atr[i]) if d == 1 else (min(o[i], trig) - SLIP_ATR * atr[i])
                    stop = od["stop"]
                    risk = abs(fill - stop)
                    if risk <= 0 or (d == 1 and stop >= fill) or (d == -1 and stop <= fill):
                        continue
                    tgt = fill + d * target_r * risk if target_r else None
                    pos = dict(dir=d, entry=fill, stop=stop, stop0=stop, target=tgt, i=i)
                    state["filled_day"] = tday[i]
                    state.setdefault("fills", {}).setdefault(tday[i], set()).add(d)
                    # same-bar stop (conservative): if the bar closed beyond the stop
                    if (d == 1 and c[i] <= stop) or (d == -1 and c[i] >= stop):
                        book.record(df, i, i, d, fill, stop, stop, "stop")
                        pos = None
                    break
        orders = orders_fn(df, i, state) if not closing else []
        if trend is not None:
            orders = [od for od in orders if od["dir"] == trend[i]]
        # no new orders whose fill bar would start at or after last_entry_ny (New York hours)
        if last_entry_ny is not None and ny_h[i] + tf_h >= last_entry_ny and ny_h[i] < 18.0:
            orders = []
        if max_losses_day is not None:
            lc = state.setdefault("loss_count", {})
            while state.get("seen", 0) < len(book.trades):
                tr = book.trades[state.get("seen", 0)]
                if tr["r"] < 0:
                    lc[tday[tr["exit_i"]]] = lc.get(tday[tr["exit_i"]], 0) + 1
                state["seen"] = state.get("seen", 0) + 1
            if lc.get(tday[i], 0) >= max_losses_day:
                orders = []
        state["orders"] = orders
    return pd.DataFrame(book.trades)


# ============================ concepts ============================================================

def asian_breakout(range_end=7.0, window_end=12.0, stop_mode="opposite", max_range_atr=6.0, buffer_atr=0.1):
    """Asian range (00:00 - range_end London) broken during London (range_end - window_end London).
    One trade per direction per day."""
    def fn(df, i, st):
        lh, day = df.lon_h.values[i], df.tday.values[i]
        if st.get("day") != day:
            st.update(day=day, hi=-np.inf, lo=np.inf)
        if 0 <= lh < range_end:
            st["hi"] = max(st["hi"], df.h.values[i])
            st["lo"] = min(st["lo"], df.l.values[i])
            return []
        if not (range_end <= lh < window_end) or not np.isfinite(st["hi"]):
            return []
        a = df.atr.values[i]
        rng = st["hi"] - st["lo"]
        if rng <= 0 or rng > max_range_atr * a:
            return []
        done = st.get("fills", {}).get(day, set())
        mid = (st["hi"] + st["lo"]) / 2
        out = []
        if 1 not in done:
            out.append(dict(dir=1, trigger=st["hi"] + buffer_atr * a, stop=st["lo"] if stop_mode == "opposite" else mid))
        if -1 not in done:
            out.append(dict(dir=-1, trigger=st["lo"] - buffer_atr * a, stop=st["hi"] if stop_mode == "opposite" else mid))
        return out
    return fn


def prev_day_breakout(stop_atr=1.5, start_lon=7.0, end_lon=16.0, buffer_atr=0.1):
    def fn(df, i, st):
        day = df.tday.values[i]
        if st.get("day") != day:
            st.update(day=day, pdh=st.get("dh"), pdl=st.get("dl"), dh=-np.inf, dl=np.inf)
        st["dh"] = max(st["dh"], df.h.values[i])
        st["dl"] = min(st["dl"], df.l.values[i])
        lh = df.lon_h.values[i]
        if st.get("pdh") is None or not (start_lon <= lh < end_lon):
            return []
        a = df.atr.values[i]
        done = st.get("fills", {}).get(day, set())
        out = []
        c = df.c.values[i]
        if 1 not in done and c < st["pdh"]:
            t = st["pdh"] + buffer_atr * a
            out.append(dict(dir=1, trigger=t, stop=t - stop_atr * a))
        if -1 not in done and c > st["pdl"]:
            t = st["pdl"] - buffer_atr * a
            out.append(dict(dir=-1, trigger=t, stop=t + stop_atr * a))
        return out
    return fn


def ny_orb(or_minutes=60, stop_mode="opposite", end_ny=15.0, buffer_atr=0.05):
    """Opening range from 09:30 NY for or_minutes, then breakout until end_ny."""
    or_end = 9.5 + or_minutes / 60

    def fn(df, i, st):
        nh, day = df.ny_h.values[i], df.tday.values[i]
        if st.get("day") != day:
            st.update(day=day, hi=-np.inf, lo=np.inf)
        if 9.5 <= nh < or_end:
            st["hi"] = max(st["hi"], df.h.values[i])
            st["lo"] = min(st["lo"], df.l.values[i])
            return []
        if not (or_end <= nh < end_ny) or not np.isfinite(st["hi"]):
            return []
        a = df.atr.values[i]
        done = st.get("fills", {}).get(day, set())
        mid = (st["hi"] + st["lo"]) / 2
        out = []
        if 1 not in done:
            out.append(dict(dir=1, trigger=st["hi"] + buffer_atr * a, stop=st["lo"] if stop_mode == "opposite" else mid))
        if -1 not in done:
            out.append(dict(dir=-1, trigger=st["lo"] - buffer_atr * a, stop=st["hi"] if stop_mode == "opposite" else mid))
        return out
    return fn


def donchian(hours=24, stop_atr=2.0):
    """Break of the highest high / lowest low of the last `hours`, stop stop_atr ATR away."""
    def fn(df, i, st):
        n = max(int(round(hours / df.tf_h.values[0])), 2)
        if i < n:
            return []
        hh = df.h.values[i - n + 1:i + 1].max()
        ll = df.l.values[i - n + 1:i + 1].min()
        a = df.atr.values[i]
        return [dict(dir=1, trigger=hh + 0.05 * a, stop=hh + 0.05 * a - stop_atr * a),
                dict(dir=-1, trigger=ll - 0.05 * a, stop=ll - 0.05 * a + stop_atr * a)]
    return fn


def chandelier(mult=3.0):
    def fn(df, i, pos):
        a = df.atr.values[i]
        seg_h = df.h.values[pos["i"]:i + 1].max()
        seg_l = df.l.values[pos["i"]:i + 1].min()
        return seg_h - mult * a if pos["dir"] == 1 else seg_l + mult * a
    return fn


# ============================ scoring ===============================================================

def score(t):
    if len(t) == 0:
        return dict(n=0, R=0.0, pf=0.0, dd=0.0, win=0.0)
    r = t.r.values
    cum = np.concatenate([[0], np.cumsum(r)])
    return dict(n=len(r), R=round(r.sum(), 1), pf=round(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), 2),
                dd=round(np.max(np.maximum.accumulate(cum) - cum), 1), win=round((r > 0).mean(), 2))


def split(t, a, b):
    if len(t) == 0:
        return t
    return t[(t.entry_time >= pd.Timestamp(a, tz="UTC")) & (t.entry_time < pd.Timestamp(b, tz="UTC"))]
