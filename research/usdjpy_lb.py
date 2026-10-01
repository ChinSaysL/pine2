"""USDJPY London breakout of the Asian range - robustness, intervention stress, overlap with Nasdaq/gold."""
import warnings; warnings.filterwarnings("ignore")
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import fx


def lb(sym="USDJPY", exit_hm=960, last_entry=660, floor=0.3, buf=0.1, worst_fill=False):
    d, cost = fx.load(sym, "M15"); out = []
    for day, x in d.groupby("lon_date"):
        asia = x[x.lon_hm < 420]; sess = x[(x.lon_hm >= 420) & (x.lon_hm < exit_hm)]
        if len(asia) < 20 or len(sess) < 8: continue
        a = x.datr.iloc[-1]
        if np.isnan(a): continue
        hi, lo = asia.h.max(), asia.l.min(); rg = hi - lo; up, dn = hi + buf * rg, lo - buf * rg
        win = sess[sess.lon_hm < last_entry]
        for k, b in enumerate(win.itertuples()):
            u, w = b.h >= up, b.l <= dn
            if u and w: break
            if u or w:
                dr = 1 if u else -1; e = max(b.o, up) if u else min(b.o, dn)
                st = lo if dr == 1 else hi
                if (e - st) * dr < floor * a: st = e - dr * floor * a
                risk = (e - st) * dr; px = xt = None
                for c in sess.iloc[k:].itertuples():
                    if (dr == 1 and c.l <= st) or (dr == -1 and c.h >= st):
                        px = st
                        if worst_fill and (c.h - c.l) > 3 * a / 8:          # violent bar: filled at its extreme
                            px = c.l if dr == 1 else c.h
                        xt = c.utc; break
                if px is None: px, xt = sess.c.iloc[-1], sess.utc.iloc[-1] + pd.Timedelta(minutes=15)
                out.append(dict(entry_time=b.utc, exit_time=xt, r=((px - e) * dr - cost) / risk, risk_pct=100 * risk / e)); break
    return pd.DataFrame(out)


VARS = {"base exit16:00": {}, "exit 14:00": dict(exit_hm=840), "exit 15:00": dict(exit_hm=900), "exit 16:30": dict(exit_hm=990),
        "exit 17:00": dict(exit_hm=1020), "entries until 10:00": dict(last_entry=600), "entries until 12:00": dict(last_entry=720),
        "floor 0.2": dict(floor=0.2), "floor 0.5": dict(floor=0.5), "buffer 0": dict(buf=0.0), "buffer 0.2": dict(buf=0.2),
        "WORST-FILL stress": dict(worst_fill=True)}


def job(n):
    t = lb(**VARS[n]); t["name"] = n; return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, list(VARS))
    t = pd.concat(res); t.to_pickle("usdjpy_lb.pkl")
    t["y"] = t.entry_time.dt.year
    pd.set_option("display.width", 260)
    tab = t.pivot_table(index="name", columns="y", values="r", aggfunc="sum").round(1)
    tab["total"] = tab.sum(axis=1); tab["yrs+"] = (tab.drop(columns="total") > 0).sum(axis=1)
    print(tab.to_string())
    b = t[t.name == "base exit16:00"]
    print("\nbase: n", len(b), "win%", round((b.r > 0).mean() * 100, 1), "avg R", round(b.r.mean(), 3), "worst", round(b.r.min(), 2),
          "best", round(b.r.max(), 2), "median stop % of price", round(b.risk_pct.median(), 3))
    w = t[t.name == "WORST-FILL stress"]
    print("worst-fill stress: worst trades", w.r.nsmallest(5).round(2).tolist(), "dates", w.nsmallest(5, "r").entry_time.dt.date.tolist())
    # overlap with Nasdaq trades (same day) and correlation of daily R
    nq = pd.read_csv("mt5_nq_ftmo2.csv", sep=";"); nq["d"] = pd.to_datetime(nq.entry_time_ny).dt.date
    b = b.assign(d=b.entry_time.dt.tz_convert("America/New_York").dt.date)
    m = b.groupby("d").r.sum().to_frame("jpy").join(nq.groupby("d").r.sum().rename("nq"), how="inner")
    print("days with both USDJPY and Nasdaq trades:", len(m), " correlation of daily R:", round(m.jpy.corr(m.nq), 3))
