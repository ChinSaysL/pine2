"""H1 trade simulator for the gold engine.

Replays the REAL entries (with their real ATR) through the local H1 bars and applies the EA's
management rules, so structural variants can be tested quickly (thousands of trades per second)
before anything goes near the MT5 tester.

Rules mirrored from GoldTrendBreakout.mq5:
  initial stop      entry -/+ InpStopAtr * ATR
  add at +InpAddAtR * R (InpAddAtR = 0 -> off); after the add the stop of both units goes to the
                    first entry (breakeven)
  trailing stop     at each bar close: ext = extreme of [entry bar .. previous bar];
                    stop = ext -/+ InpTrailAtr * ATR
  session flat      exit at the close of the first bar whose time is in 16:50-18:00 New York
Variants: stop multiplier, trail multiplier, add levels (list), breakeven-after-add,
time-stop (bars / required R), reverse-after-stop (fade the failed breakout).
"""
import numpy as np
import pandas as pd

R_DIR = r"c:\Users\Abdo\Downloads\pine2\research"


def load():
    t = pd.read_csv(R_DIR + r"\mt5_bm_halfrisk.csv", sep=";")
    t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
    t["xt"] = pd.to_datetime(t.exit_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
    t = t.dropna(subset=["et", "xt"])
    t["et_utc"] = t.et.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    t = t.dropna(subset=["et_utc"])
    t["dist"] = (t.risk_usd / (t.lots * 100)).abs()
    t["atr"] = t.dist / 2.0                       # the export ran with InpStopAtr = 2
    t["dirn"] = np.where(t.dir == "L", 1, -1)
    h = pd.read_csv(R_DIR + r"\data\XAUUSD_H1.csv", parse_dates=["utc"]).sort_values("utc").reset_index(drop=True)
    h["ny"] = h.utc.dt.tz_convert("America/New_York")
    h["nymin"] = h.ny.dt.hour * 60 + h.ny.dt.minute
    t = t[(t.et_utc >= h.utc.min()) & (t.et_utc <= h.utc.max())].reset_index(drop=True)
    return t, h


def stats(df, label="", col="r"):
    r = df[col].dropna().values
    if not len(r):
        return dict(label=label, n=0, total=0.0, pf=0.0, win=0, avg=0.0)
    pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
    return dict(label=label, n=len(r), total=round(r.sum(), 1), pf=round(pf, 2),
                win=round(100 * (r > 0).mean()), avg=round(r.mean(), 3))


def simulate(t, h, stop_atr=2.0, trail_atr=3.0, add_levels=(1.0,), be_after_add=True,
             time_stop_bars=0, time_stop_min_r=0.0,
             reverse=False, rev_stop_atr=1.0, rev_trail_atr=2.0, rev_max_bars=24, rev_same_dir=False,
             session_flat=True, trail_from_entry_bar=False):
    """Per real entry, replay the trade on the H1 bars and return its R.

    Unit based: the initial entry and every add is a unit risking the same fixed % of equity,
    1R = one unit's risk, so R is additive (the EA risks riskNow again on the add, and all
    positions share one stop).
    """
    utc = h.utc.values
    hi, lo, cl = h.high.values, h.low.values, h.close.values
    nymin = h.nymin.values
    out = []
    for tr in t.itertuples():
        atr = tr.atr
        if not np.isfinite(atr) or atr <= 0:
            continue
        d = tr.dirn
        risk = stop_atr * atr                      # 1R in price (one unit)
        entry = tr.entry
        shared_stop = entry - d * risk
        units = [[entry, shared_stop]]             # [entry, stop] per unit
        nadd = 0
        i0 = int(np.searchsorted(utc, np.datetime64(tr.et_utc.replace(tzinfo=None))))
        i0 = max(min(i0, len(h) - 1), 0)
        realized = 0.0
        rev_r = np.nan
        why = "eod"
        for i in range(i0, min(i0 + 2000, len(h))):
            # --- stops hit inside this bar (shared stop) ---
            if (d == 1 and lo[i] <= shared_stop) or (d == -1 and hi[i] >= shared_stop):
                for u in units:
                    realized += (shared_stop - u[0]) * d / risk
                why = "stop"
                if reverse:
                    q = d if rev_same_dir else -d          # +1/-1 = direction of the second trade
                    rrisk = rev_stop_atr * atr
                    rentry = shared_stop
                    rstop = rentry - q * rrisk
                    rbest = rentry
                    for j in range(i, min(i + rev_max_bars, len(h))):
                        if (q == 1 and lo[j] <= rstop) or (q == -1 and hi[j] >= rstop):
                            realized_rev = (rstop - rentry) * q / rrisk
                            break
                        rbest = max(rbest, hi[j]) if q == 1 else min(rbest, lo[j])
                        if j > i:
                            rtrail = rbest - q * rev_trail_atr * atr
                            rstop = max(rstop, rtrail) if q == 1 else min(rstop, rtrail)
                        if session_flat and 16 * 60 + 45 < (nymin[j] + 60) % 1440 <= 18 * 60:
                            realized_rev = (cl[j] - rentry) * q / rrisk
                            break
                    else:
                        jj = min(i + rev_max_bars, len(h) - 1)
                        realized_rev = (cl[jj] - rentry) * q / rrisk
                    rev_r = realized_rev
                    break
                break
            # --- add to the winner ---
            if nadd < len(add_levels):
                lvl = entry + d * add_levels[nadd] * risk
                if (d == 1 and hi[i] >= lvl) or (d == -1 and lo[i] <= lvl):
                    units.append([lvl, shared_stop])
                    nadd += 1
                    if be_after_add:
                        shared_stop = max(shared_stop, entry) if d == 1 else min(shared_stop, entry)
            # --- trailing stop (EA: only once the entry bar is 2+ bars back; extreme up to the
            #     previous bar, the just-closed one included) ---
            if i - i0 >= 2:
                seg = hi[i0:i]
                ext = seg.max() if d == 1 else lo[i0:i].min()
                trail = ext - d * trail_atr * atr
                shared_stop = max(shared_stop, trail) if d == 1 else min(shared_stop, trail)
            # --- time stop ---
            if time_stop_bars and (i - i0) >= time_stop_bars and (cl[i] - entry) * d / risk < time_stop_min_r:
                for u in units:
                    realized += (cl[i] - u[0]) * d / risk
                why = "time"
                break
            # --- session flat: the EA acts at the close of the bar whose close time is in
            #     (16:45, 18:00] New York, i.e. the 16:00-17:00 bar dies at its 17:00 close ---
            if session_flat and 16 * 60 + 45 < (nymin[i] + 60) % 1440 <= 18 * 60:
                for u in units:
                    realized += (cl[i] - u[0]) * d / risk
                why = "session"
                break
        else:
            jj = min(i0 + 1999, len(h) - 1)
            for u in units:
                realized += (cl[jj] - u[0]) * d / risk
        out.append(dict(et=tr.et_utc, r=realized, rev=rev_r, why=why, year=tr.et.year, dir=d, units=len(units)))
    return pd.DataFrame(out)
