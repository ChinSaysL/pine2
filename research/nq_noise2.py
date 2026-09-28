"""Noise-area engine improvements (FTMO US100 M5, 2021-09..2026-09). Logic changes, fixed in advance.
BASE   as the EA: entry checks at bar ends 10:00-15:00 (every 30 min), one trade a day, hard stop at the band or VWAP
       (farther, floor 0.3 cash ATR), exit when a 30-min check closes back inside the band / across VWAP, or 15:55.
REENTRY up to 3 trades a day (a new breakout at a later check after an exit).
EXIT5   the exit test runs on every 5-min close (not only at :00/:30).
SERVER  a trailing stop at max(band, VWAP) (long) held on the server, moved every bar (only in the trade's favour).
CUT13   no new entries after 13:00 (only if late entries are weak in every era - see the diagnostics).
Diagnostics: R by entry time, by agreement with the morning's opening trade, by band width.
Sigma from the last 14 full sessions (Fed days included, as in the EA). R per trade, cost 2 x median spread."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
from newfam import FOMC

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
FOMC_D = {pd.Timestamp(x).date() for x in FOMC}


def sessions():
    d = pd.read_csv(f"{DATA}\\FT_US100.cash_M5.csv"); d["utc"] = pd.to_datetime(d.utc, utc=True)
    d = d[d.utc >= "2021-06-01"]
    ny = d.utc.dt.tz_convert("America/New_York")
    d["date"], d["hm"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "tick_volume": "v"})
    cash = d[(d.hm >= 570) & (d.hm < 960)]
    S = {k: x.reset_index(drop=True) for k, x in cash.groupby("date") if x.hm.iat[0] == 570}
    keys = list(S)
    D = pd.DataFrame({k: dict(h=x.h.max(), l=x.l.min(), c=x.c.iat[-1], n=len(x)) for k, x in S.items()}).T
    D[["h", "l", "c"]] = D[["h", "l", "c"]].astype(float)
    tr = np.maximum(D.h - D.l, np.maximum((D.h - D.c.shift()).abs(), (D.l - D.c.shift()).abs()))
    D["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1); D["pc"] = D.c.shift(1)
    meta = pd.read_csv(f"{DATA}\\FT_meta.csv").query("sym == 'US100.cash' and tf == 'M5'").iloc[0]
    return S, keys, D, 2 * meta.spread_med * 0.01


def orb_dir(x):
    f = x.iloc[:3]; o0, c0, hi, lo = f.o.iat[0], f.c.iat[-1], f.h.max(), f.l.min()
    if c0 == o0 or hi == lo or abs(c0 - o0) < 0.2 * (hi - lo): return 0
    return 1 if c0 > o0 else -1


def run(S, keys, D, cost, max_trades=1, exit5=False, server=False, last_entry=900, exit_mode="band_vwap", confirm=False, confirm_n=1):
    out = []
    full = [k for k in keys if D.n[k] >= 78]
    for i, day in enumerate(keys):
        x = S[day]
        if day in FOMC_D or D.n[day] < 70 or day < pd.Timestamp("2021-09-01").date(): continue
        hist = [k for k in full if k < day][-14:]
        if len(hist) < 10 or np.isnan(D.pc[day]) or np.isnan(D.atr[day]): continue
        L = len(x)
        mv = np.array([np.abs(S[k].c.values[:L] / S[k].o.iat[0] - 1) for k in hist if len(S[k]) >= L])
        if len(mv) < 10: continue
        sig = mv.mean(axis=0); o = x.o.iat[0]; pc = D.pc[day]; a = D.atr[day]
        ub = max(o, pc) * (1 + sig); lb = min(o, pc) * (1 - sig)
        tp = (x.h + x.l + x.c) / 3; vv = x.v.replace(0, 1); vwap = ((tp * vv).cumsum() / vv.cumsum()).values
        hm = x.hm.values; c = x.c.values; od = orb_dir(x)
        n_tr = 0; k = 0
        while k < L - 1 and n_tr < max_trades:
            if not (hm[k] >= 595 and (hm[k] + 5) % 30 == 0 and hm[k] < last_entry):
                k += 1; continue
            dr = 1 if c[k] > ub[k] else (-1 if c[k] < lb[k] else 0)
            if not dr: k += 1; continue
            if confirm:                                     # still outside the band at the next half-hour check
                okc = True; k2 = k
                for _ in range(confirm_n):
                    k2 += 6
                    if k2 >= L - 1 or hm[k2] >= last_entry or not ((dr == 1 and c[k2] > ub[k2]) or (dr == -1 and c[k2] < lb[k2])):
                        okc = False; break
                if not okc: k += 1; continue
                k = k2
            e = x.o.iat[k + 1]
            st = min(ub[k], vwap[k]) if dr == 1 else max(lb[k], vwap[k])
            if (e - st) * dr < 0.3 * a: st = e - dr * 0.3 * a
            R = (e - st) * dr; px = None; j = k + 1
            for j in range(k + 1, L):
                b = x.iloc[j]
                if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st):
                    px = min(b.o, st) if dr == 1 else max(b.o, st); break
                trail = (max(ub[j], vwap[j]) if dr == 1 else min(lb[j], vwap[j])) if exit_mode == "band_vwap" else (ub[j] if dr == 1 else lb[j])
                if server:
                    st = max(st, trail) if dr == 1 else min(st, trail)
                chk = exit5 or (hm[j] + 5) % 30 == 0
                if (exit_mode != "hold" and chk and (c[j] - trail) * dr < 0) or hm[j] >= 955:
                    px = c[j]; break
            if px is None: px = c[-1]
            out.append(dict(day=day, entry_time=x.utc.iat[k + 1], exit_time=x.utc.iat[j] + pd.Timedelta(minutes=5), entry_hm=hm[k] + 5, r=((px - e) * dr - cost) / R, dir=dr, orb=od,
                            band_pct=sig[k] * 100, exit_hm=hm[j]))
            n_tr += 1; k = j + 1
    return pd.DataFrame(out)


VARS = {"BASE": {}, "REENTRY (<=3/day)": dict(max_trades=3), "EXIT5 (5-min exit test)": dict(exit5=True),
        "SERVER trailing stop": dict(server=True), "CUT13 (entries until 13:00)": dict(last_entry=780),
        "REENTRY + SERVER": dict(max_trades=3, server=True)}


def job(n):
    S, keys, D, cost = sessions()
    t = run(S, keys, D, cost, **VARS[n]); t["v"] = n; return t


if __name__ == "__main__":
    with Pool(len(VARS)) as p:
        T = pd.concat(p.map(job, list(VARS)))
    T["day"] = pd.to_datetime(T.day); T["era"] = np.select([T.day < "2024-01-01", T.day < "2026-01-01"], ["2021-23", "2024-25"], "2026")
    T.to_pickle("nq_noise2.pkl")
    pd.set_option("display.width", 250)
    rows = []
    for v, t in T.groupby("v", sort=False):
        row = {"variant": v}
        for e, x in t.groupby("era"):
            row[e] = f"{x.r.sum():+6.1f}R n={len(x):3d} avg {x.r.mean():+.3f}"
        row["total"] = round(t.r.sum(), 1); row["PF"] = round(t.r[t.r > 0].sum() / -t.r[t.r < 0].sum(), 2)
        rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))
    b = T[T.v == "BASE"].copy()
    b["entry_bucket"] = pd.cut(b.entry_hm, [0, 630, 690, 780, 900], labels=["10:00-10:30", "11:00-11:30", "12:00-13:00", "13:30-15:00"])
    print("\nBASE by entry time (avg R | n):"); print(b.groupby(["entry_bucket", "era"]).r.agg(["mean", "count"]).round(3).unstack("era").to_string())
    b["vs_orb"] = np.select([b.orb == 0, b.orb == b.dir], ["no opening trade", "same direction"], "opposite")
    print("\nBASE vs the morning opening trade (avg R | n):"); print(b.groupby(["vs_orb", "era"]).r.agg(["mean", "count"]).round(3).unstack("era").to_string())
    b["band"] = pd.qcut(b.band_pct, 3, labels=["narrow band", "mid", "wide band"])
    print("\nBASE by band width (avg R | n):"); print(b.groupby(["band", "era"]).r.agg(["mean", "count"]).round(3).unstack("era").to_string())
