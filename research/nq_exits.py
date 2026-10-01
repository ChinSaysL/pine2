"""Exit experiments for the Nasdaq EA.

Part 1: replay the real challenge trades of 2026-09-29/30 bar by bar (M5, FTMO data): how far
        in profit each got (MFE), when it peaked, and what other exit rules would have paid.
Part 2: the same rules over the whole FTMO US100.cash M5 history (2021-09..2026-09) on both
        streams (opening range + noise engine), so we pick a rule that helps the wasted trades
        without wrecking the rest.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
END_HM = 955          # 15:55 New York, the live session exit
CHECK_EVERY = 30      # the noise engine only looks every half hour


def load_days(with_recent=True):
    parts = [pd.read_csv(f"{DATA}\\FT_US100.cash_M5.csv")]
    if with_recent:
        try:
            parts.append(pd.read_csv(f"{DATA}\\FT_US100.cash_M5_recent.csv"))
        except FileNotFoundError:
            pass
    d = pd.concat(parts).drop_duplicates(subset=["utc"]).sort_values("utc")
    d["utc"] = pd.to_datetime(d.utc, utc=True)
    ny = d.utc.dt.tz_convert("America/New_York")
    d["date"], d["hm"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "tick_volume": "v"})
    cash = d[(d.hm >= 570) & (d.hm < 960)]
    days = {k: x.reset_index(drop=True) for k, x in cash.groupby("date") if x.hm.iat[0] == 570 and len(x) >= 70}
    D = pd.DataFrame({k: dict(o=x.o.iat[0], h=x.h.max(), l=x.l.min(), c=x.c.iat[-1]) for k, x in days.items()}).T.astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    D["pc"] = D.c.shift(1)
    return days, D, 2 * 1.45      # round trip = 2 x 1.45 points (median FTMO spread on US100.cash)


RULES = {
    "live: fixed stop -> 15:55":               dict(),
    "BE at +0.5R":                             dict(be=0.5),
    "BE at +1R":                               dict(be=1.0),
    "trail 0.5R after +1R":                    dict(trail_after=1.0, trail=0.5),
    "trail 1R after +2R":                      dict(trail_after=2.0, trail=1.0),
    "BE 0.5R + trail 0.5R after +1R":          dict(be=0.5, trail_after=1.0, trail=0.5),
    "TP +1R":                                  dict(tp=1.0),
    "TP +1.5R":                                dict(tp=1.5),
    "BE 0.5R + TP +1.5R":                      dict(be=0.5, tp=1.5),
    "time exit 13:00 if < 0R":                 dict(tstop=780),
    "BE 0.5R + time exit 14:00 if <0.2R":      dict(be=0.5, tstop=840, tstop_min=0.2),
    "afternoon: BE at 13:00 if >= +0.5R":      dict(be_at=780, be_at_min=0.5),
    "afternoon: BE at 14:00 if >= +0.5R":      dict(be_at=840, be_at_min=0.5),
    "afternoon BE 13:00 + trail 0.5R at +1.5R": dict(be_at=780, be_at_min=0.5, trail_after=1.5, trail=0.5),
}



def walk(x, k0, dr, e, st, cost, rule, exit_level=None):
    """Walk bars from k0. Stop first inside a bar (conservative), then take profit, then the
    break-even / trail update, then the noise exit, then the optional time stop, then 15:55."""
    R = (e - st) * dr
    if R <= 0:
        return None
    best, stop = e, st
    for k in range(k0, len(x)):
        b = x.iloc[k]
        if (dr == 1 and b.l <= stop) or (dr == -1 and b.h >= stop):
            px = min(b.o, stop) if dr == 1 else max(b.o, stop)
            return ((px - e) * dr - cost) / R, b.hm, "stop"
        up = (b.h - e) * dr / R
        if "tp" in rule and up >= rule["tp"]:
            return rule["tp"] - cost / R, b.hm, "target"
        best = max(best, b.h) if dr == 1 else min(best, b.l)
        bestr = (best - e) * dr / R
        if "be" in rule and bestr >= rule["be"]:
            be_px = e + dr * cost / 2
            stop = max(stop, be_px) if dr == 1 else min(stop, be_px)
        if "trail_after" in rule and bestr >= rule["trail_after"]:
            cand = best - dr * rule["trail"] * R
            stop = max(stop, cand) if dr == 1 else min(stop, cand)
        if exit_level is not None and (b.hm + 5) % CHECK_EVERY == 0:
            if (b.c - exit_level[k]) * dr < 0:
                return ((b.c - e) * dr - cost) / R, b.hm, "noise"
        if "tstop" in rule and b.hm >= rule["tstop"] and (b.c - e) * dr / R < rule.get("tstop_min", 0.0):
            return ((b.c - e) * dr - cost) / R, b.hm, "time"
        # optional protection that only kicks in late in the day (the "gave it all back" pattern)
        if "be_at" in rule and b.hm >= rule["be_at"] and (b.c - e) * dr / R >= rule.get("be_at_min", 0.5):
            be_px = e + dr * cost / 2
            stop = max(stop, be_px) if dr == 1 else min(stop, be_px)
        if b.hm >= END_HM:
            return ((b.c - e) * dr - cost) / R, b.hm, "session"
    last = x.iloc[-1]
    return ((last.c - e) * dr - cost) / R, last.hm, "end"



def orb_setup(x, D, day):
    """The live opening-range entry: the first 15 min set the direction, entry next bar open,
    stop at the range's other side (floor 0.3 x cash ATR)."""
    a = D.atr[day]
    if np.isnan(a):
        return None
    f = x.iloc[:3]
    o0, c0, hi, lo = f.o.iat[0], f.c.iat[-1], f.h.max(), f.l.min()
    if c0 == o0:
        return None
    dr = 1 if c0 > o0 else -1
    e, st = x.o.iat[3], (lo if dr == 1 else hi)
    if (e - st) * dr < 0.3 * a:
        st = e - dr * 0.3 * a
    return dr, e, st, 3


def peak_r(x, k0, dr, e, st, exit_level=None):
    """Max favourable excursion in R while the trade is alive (rule independent)."""
    R = (e - st) * dr
    best = e
    for k in range(k0, len(x)):
        b = x.iloc[k]
        if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st):
            break
        best = max(best, b.h) if dr == 1 else min(best, b.l)
        if exit_level is not None and (b.hm + 5) % CHECK_EVERY == 0 and (b.c - exit_level[k]) * dr < 0:
            break
        if b.hm >= END_HM:
            break
    return (best - e) * dr / R


# ------------------------------------------------------------------ Part 1: the real trades
LIVE = [
    dict(label="2026-09-29 NQ ORB SELL",  day="2026-09-29", dr=-1, entry=30295.43, stop=30445.48, lots=0.59, k_hm=585, real=-19.18),
    dict(label="2026-09-30 NQ ORB BUY",   day="2026-09-30", dr=+1, entry=30497.78, stop=30380.04, lots=0.81, k_hm=585, real=-48.40),
    dict(label="2026-09-30 NQ NOISE BUY", day="2026-09-30", dr=+1, entry=30574.03, stop=30452.39, lots=0.81, k_hm=840, real=-0.81),
]


def part1(days, cost):
    for tr in LIVE:
        day = pd.Timestamp(tr["day"]).date()
        if day not in days:
            print(f"{tr['label']}: no bars for {day}")
            continue
        x = days[day]
        k0 = int(np.argmax((x.hm >= tr["k_hm"]).values))
        R = abs(tr["entry"] - tr["stop"])
        pk = peak_r(x, k0, tr["dr"], tr["entry"], tr["stop"])
        path = " ".join(f"{int(b.hm // 60):02d}:{int(b.hm % 60):02d} {((b.c - tr['entry']) * tr['dr']) / R:+.2f}"
                        for b in x.iloc[k0:].itertuples() if b.hm % 30 == 0)
        print(f"\n=== {tr['label']}  entry {tr['entry']}  stop {tr['stop']}  R={R:.2f} pts  "
              f"({tr['lots']} lots -> 1R = {tr['lots'] * R:.0f} USD)")
        print(f"    peak while alive: +{pk:.2f}R  ({pk * tr['lots'] * R:+.2f} USD)      actual result: {tr['real']:+.2f} USD")
        print(f"    path (NY, R at each half hour): {path}")
        print("    what other exits would have paid:")
        for name, rule in RULES.items():
            r = walk(x, k0, tr["dr"], tr["entry"], tr["stop"], cost, rule)
            if r is None:
                continue
            print(f"      {name:38s} {r[0]:+6.2f}R {r[0] * tr['lots'] * R:+8.2f} USD   exit "
                  f"{int(r[1] // 60):02d}:{int(r[1] % 60):02d} ({r[2]})")


# ------------------------------------------------------------------ Part 2: whole history
def noise_entry(days, keys, i, D):
    """First noise-area signal of the day: returns (dr, entry, stop, k0, level_array)."""
    day = keys[i]
    if i < 14:
        return None
    a, pc = D.atr[day], D.pc[day]
    if np.isnan(a) or np.isnan(pc):
        return None
    x = days[day]
    hist = [(days[keys[j]].c / days[keys[j]].o.iat[0] - 1).abs().values
            for j in range(i - 14, i) if len(days[keys[j]]) == len(x)]
    if len(hist) < 10:
        return None
    sig = np.mean(hist, axis=0)
    o = x.o.iat[0]
    ub, lb = max(o, pc) * (1 + sig), min(o, pc) * (1 - sig)
    tp = (x.h + x.l + x.c) / 3
    vv = x.v.replace(0, 1)
    vwap = ((tp * vv).cumsum() / vv.cumsum()).values
    for k in range(len(x)):
        hm, c = x.hm.iat[k], x.c.iat[k]
        if not (hm >= 595 and (hm + 5) % CHECK_EVERY == 0 and hm < 900):
            continue
        if c > ub[k]:
            risk = max(abs(c - ub[k]), abs(c - vwap[k]), 0.3 * a)
            return 1, c, c - risk, k + 1, np.maximum(ub, vwap)
        if c < lb[k]:
            risk = max(abs(c - lb[k]), abs(c - vwap[k]), 0.3 * a)
            return -1, c, c + risk, k + 1, np.minimum(lb, vwap)
    return None


def part2(days, D, cost):
    keys = list(days)
    rows = []
    for i, day in enumerate(keys):
        x = days[day]
        s = orb_setup(x, D, day)
        if s:
            dr, e, st, k0 = s
            pk = peak_r(x, k0, dr, e, st)
            for name, rule in RULES.items():
                r = walk(x, k0, dr, e, st, cost, rule)
                if r:
                    rows.append(dict(day=day, stream="ORB", rule=name, r=r[0], peak=pk, hm=r[1]))
        n = noise_entry(days, keys, i, D)
        if n:
            dr, e, st, k0, lvl = n
            pk = peak_r(x, k0, dr, e, st, lvl)
            for name, rule in RULES.items():
                r = walk(x, k0, dr, e, st, cost, rule, lvl)
                if r:
                    rows.append(dict(day=day, stream="NOISE", rule=name, r=r[0], peak=pk, hm=r[1]))
    t = pd.DataFrame(rows)
    t["year"] = pd.to_datetime(t.day).dt.year
    out = []
    for stream in ("ORB", "NOISE", "BOTH"):
        u = t if stream == "BOTH" else t[t.stream == stream]
        head = (f"\n================ {stream} stream, {u.rule.nunique()} rules, "
                f"{int(len(u) / max(u.rule.nunique(), 1))} trades ================")
        print(head)
        out.append(head)
        agg = u.groupby("rule").apply(lambda g: pd.Series({
            "n": len(g),
            "totR": g.r.sum(),
            "PF": g.r[g.r > 0].sum() / max(-g.r[g.r < 0].sum(), 1e-9),
            "win%": (g.r > 0).mean() * 100,
            "gave_back": ((g.peak >= 0.5) & (g.r < 0)).mean() * 100,
            "2026R": g[g.year == 2026].r.sum(),
            "worst": g.r.min(),
        }), include_groups=False).reindex(list(RULES))
        print(agg.round(2).to_string())
        out.append(agg.round(2).to_string())
        if stream == "BOTH":
            piv = u.pivot_table(index="rule", columns="year", values="r", aggfunc="sum").round(1)
            print("\nR per year (both streams together):")
            print(piv.to_string())
            out.append("\nR per year (both streams together):")
            out.append(piv.to_string())
    with open("nq_exits_summary.txt", "w", encoding="utf-8") as f:
        f.write("Nasdaq exit experiments - FTMO US100.cash M5, 1249 sessions, ORB + noise streams\n")
        f.write("R per trade measured against the trade's own 1R; round-trip cost 2 x 1.45 points\n")
        f.write("\n".join(out))
    return t


if __name__ == "__main__":
    days, D, cost = load_days()
    print(f"data: {min(days)} -> {max(days)}  ({len(days)} sessions, {sum(len(v) for v in days.values())} M5 bars)")
    part1(days, cost)
    t = part2(days, D, cost)
    t.to_pickle("nq_exits.pkl")

