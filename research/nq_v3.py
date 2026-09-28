"""Nasdaq improvements v3 - exact trade records (entry/exit timestamps, R per trade at its own 1R risk), FTMO US100 M5,
2021-09..2026-09, Fed days / short sessions skipped. Then FTMO odds with gold v2 (live policy). 14 workers.
BASE   15-min opening candle -> direction; entry next bar open; stop other side (floor 0.3 cash ATR); exit 15:55.
SAR    + if the base trade is stopped before 12:00: a SEPARATE reversal trade at the stop price, stop at the opening
         range's other side (floor 0.3 ATR), exit 15:55.
TRAIL  once the trade reaches +2R, stop trails 1R behind the best price (locks >= +1R); else as base.
NOISE  second stream: noise-area momentum with a HARD stop at the bound (or VWAP, the farther; floor 0.3 ATR) checked
         on every bar; entries checked every 30 min from 10:00 to 15:00; exit back inside bound/VWAP (30-min checks) or 15:55.
GAP    weight 1.0 when the opening candle agrees with the overnight gap, 0.5 when not (base weight 0.75)."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import ftmo_sim2 as F
import stats_summary as S
from policy_grid import trades as gold_trades
from third_combo import gold_bad_at
from nq_logic import load


def walk(x, k0, dr, e, st, trail=False):
    """From bar k0: returns (exit_px, exit_idx, stopped). Stop first inside a bar. trail: after +2R, stop = best - 1R."""
    R = (e - st) * dr; best = e
    for k in range(k0, len(x)):
        b = x.iloc[k]
        if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st):
            return (min(b.o, st) if dr == 1 else max(b.o, st)), k, True
        if trail:
            best = max(best, b.h) if dr == 1 else min(best, b.l)
            if (best - e) * dr >= 2 * R: st = max(st, best - R) if dr == 1 else min(st, best + R)
        if b.hm >= 955: return b.c, k, False
    return x.c.iat[-1], len(x) - 1, False


def day_trades(x, D, day, cost, sar=False, trail=False):
    out = []; a = D.atr[day]
    if np.isnan(a): return out
    f = x.iloc[:3]; o0, c0, hi, lo = f.o.iat[0], f.c.iat[-1], f.h.max(), f.l.min()
    if c0 == o0: return out
    dr = 1 if c0 > o0 else -1
    aligned = (not np.isnan(D.pc[day])) and np.sign(o0 - D.pc[day]) == dr
    e = x.o.iat[3]; st = lo if dr == 1 else hi
    if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
    px, k, stopped = walk(x, 3, dr, e, st, trail)
    R = (e - st) * dr
    out.append(dict(entry_time=x.utc.iat[3], exit_time=x.utc.iat[k] + pd.Timedelta(minutes=5), r=((px - e) * dr - cost) / R, aligned=aligned, kind="orb"))
    if sar and stopped and x.hm.iat[k] < 720 and k + 1 < len(x):
        d2 = -dr; e2 = px; st2 = hi if d2 == -1 else lo
        if (e2 - st2) * d2 < 0.3 * a: st2 = e2 - d2 * 0.3 * a
        if (e2 - st2) * d2 > 0:
            px2, k2, _ = walk(x, k + 1, d2, e2, st2, trail)
            out.append(dict(entry_time=x.utc.iat[k] + pd.Timedelta(minutes=5), exit_time=x.utc.iat[k2] + pd.Timedelta(minutes=5),
                            r=((px2 - e2) * d2 - cost) / ((e2 - st2) * d2), aligned=aligned, kind="sar"))
    return out


def noise(days, D, cost):
    keys = list(days); out = []
    move = {k: (x.c / x.o.iat[0] - 1).abs().values for k, x in days.items()}
    for i, day in enumerate(keys):
        if i < 14 or np.isnan(D.pc[day]) or np.isnan(D.atr[day]): continue
        x = days[day]; hist = [move[keys[j]] for j in range(i - 14, i) if len(move[keys[j]]) == len(x)]
        if len(hist) < 10: continue
        sig = np.mean(hist, axis=0); o = x.o.iat[0]; pc = D.pc[day]; a = D.atr[day]
        ub = max(o, pc) * (1 + sig); lb = min(o, pc) * (1 - sig)
        tp = (x.h + x.l + x.c) / 3; vv = x.v.replace(0, 1); vwap = ((tp * vv).cumsum() / vv.cumsum()).values
        for k in range(len(x)):
            hm = x.hm.iat[k]
            if not (hm >= 595 and (hm + 5) % 30 == 0 and hm < 900): continue
            c = x.c.iat[k]; dr = 1 if c > ub[k] else (-1 if c < lb[k] else 0)
            if not dr or k + 1 >= len(x): continue
            e = x.o.iat[k + 1]; ref = ub[k] if dr == 1 else lb[k]
            st = min(ref, vwap[k]) if dr == 1 else max(ref, vwap[k])
            if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
            R = (e - st) * dr; px = None; j = k + 1
            for j in range(k + 1, len(x)):
                b = x.iloc[j]
                if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = min(b.o, st) if dr == 1 else max(b.o, st); break
                chk = (b.hm + 5) % 30 == 0
                trail_px = max(ub[j], vwap[j]) if dr == 1 else min(lb[j], vwap[j])
                if (chk and (b.c - trail_px) * dr < 0) or b.hm >= 955: px = b.c; break
            if px is None: px = x.c.iat[-1]
            out.append(dict(entry_time=x.utc.iat[k + 1], exit_time=x.utc.iat[j] + pd.Timedelta(minutes=5), r=((px - e) * dr - cost) / R, aligned=True, kind="noise"))
            break
    return out


def build(v):
    days, D, cost = load()
    rows = []
    for day, x in days.items():
        rows += day_trades(x, D, day, cost, sar=v in ("SAR", "SAR+TRAIL", "SAR+TRAIL+GAP"), trail=v in ("TRAIL", "SAR+TRAIL", "SAR+TRAIL+GAP"))
    if v == "BASE+NOISE": rows += noise(days, D, cost)
    t = pd.DataFrame(rows); t["variant"] = v
    return t


VARS = ["BASE", "SAR", "TRAIL", "SAR+TRAIL", "BASE+NOISE", "GAP", "SAR+TRAIL+GAP"]
PREP = {}


def init():
    T = pd.read_pickle("nq_v3_trades.pkl")
    g = gold_trades(); g["mkt"] = "gold"; g = g[g.entry_time >= S.START - pd.Timedelta(days=5)]
    for v in VARS:
        t = T[T.variant == ("BASE" if v == "GAP" else v.replace("+GAP", ""))].copy()
        t["w"] = 0.75
        if "GAP" in v: t["w"] = np.where(t.aligned, 1.0, 0.5)
        t["stop"] = t.r < -0.5; t["mkt"] = "nasdaq"
        b = pd.concat([g, t[["entry_time", "exit_time", "r", "w", "stop", "mkt"]]]).sort_values("entry_time").reset_index(drop=True)
        PREP[v] = (b,) + F.prepare(b)[1:]


def job(a):
    v, s = a; t, ev, days = PREP[v]; out = dict(v=v, start=s)
    for h in (30, 60, 90):
        b, m, w, p, st, _, lo = S.sim(t, ev, days, s, h, target=10.0)
        out[f"pass{h}"], out[f"stuck{h}"], out[f"wd{h}"], out[f"low{h}"] = p, st, w, lo
    return out


def month(a):
    v, s = a; t, ev, days = PREP[v]
    b, *_ = S.sim(t, ev, days, s, ((s + pd.offsets.MonthBegin(1)) - s).days)
    return dict(v=v, start=s, pnl=b)


if __name__ == "__main__":
    with Pool(7) as p:
        T = pd.concat(p.map(build, [v for v in VARS if v not in ("GAP", "SAR+TRAIL+GAP")]))
    T.to_pickle("nq_v3_trades.pkl")
    print("R per variant (each trade 1R):")
    for v, t in T.groupby("variant", sort=False):
        y = t.groupby(t.entry_time.dt.year).r.sum().round(1).to_dict()
        print(f"  {v:11s} n={len(t):4d} total {t.r.sum():+6.1f}R PF {t.r[t.r > 0].sum() / -t.r[t.r < 0].sum():.2f} | by year {y}")
    init()
    months = list(pd.date_range("2021-10-01", "2026-09-01", freq="MS", tz="Europe/Prague"))
    with Pool(14, initializer=init) as p:
        res = pd.DataFrame(p.map(job, list(itertools.product(VARS, S.STARTS)), chunksize=30))
        mo = pd.DataFrame(p.map(month, list(itertools.product(VARS, months)), chunksize=10))
    res["bad"] = gold_bad_at(pd.Series(res.start).dt.tz_convert("UTC"))
    res["era"] = np.where(res.start < pd.Timestamp("2024-01-01", tz="UTC"), "21-23", "24-26")
    g = res.groupby("v", sort=False); gm = mo.groupby("v", sort=False)
    tab = pd.DataFrame({"pass30": g.pass30.mean(), "pass60": g.pass60.mean(), "pass90": g.pass90.mean(), "stuck90": g.stuck90.mean(),
                        "p60 21-23": res[res.era == "21-23"].groupby("v", sort=False).pass60.mean(),
                        "p60 24-26": res[res.era == "24-26"].groupby("v", sort=False).pass60.mean(),
                        "p60 gold-BAD start": res[res.bad].groupby("v", sort=False).pass60.mean(),
                        "avg month %": gm.pnl.mean(), "months +": gm.pnl.apply(lambda v: (v > 0).mean()),
                        "2026 avg month %": mo[mo.start >= pd.Timestamp("2026-01-01", tz="UTC")].groupby("v", sort=False).pnl.mean(),
                        "worst day": g.wd90.min(), "lowest": g.low90.min()})
    pd.set_option("display.width", 300)
    print(tab.round(3).to_string())
