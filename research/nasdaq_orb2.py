import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
from indices import load, daily

def orb_floor(floor_atr, lev_cap=None):
    d, cost = load("US100.cash"); D = daily(d)
    out = []
    for day, x in d[(d.hm >= 570) & (d.hm < 960)].groupby("date"):
        if day not in D.index or len(x) < 20 or x.hm.iloc[0] != 570: continue
        o0, c0, hi, lo = x.o.iloc[0], x.c.iloc[0], x.h.iloc[0], x.l.iloc[0]
        a = D.atr[day]
        if c0 == o0 or np.isnan(a): continue
        dr = 1 if c0 > o0 else -1
        rest = x.iloc[1:]; e = rest.o.iloc[0]
        st = lo if dr == 1 else hi
        if (e - st) * dr < floor_atr * a: st = e - dr * floor_atr * a
        risk = (e - st) * dr
        if risk <= 0: continue
        px = None
        for b in rest.itertuples():
            if (dr == 1 and b.l <= st) or (dr == -1 and b.h >= st): px = st; break
            if b.hm >= 945: px = b.c; break
        if px is None: px = rest.c.iloc[-1]
        out.append(dict(entry_time=rest.utc.iloc[0], r=((px - e) * dr - cost) / risk, risk_pct=100 * risk / e))
    t = pd.DataFrame(out); t["floor"] = floor_atr
    return t

if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(orb_floor, [0.0, 0.1, 0.2, 0.3, 0.5])
    pd.set_option("display.width", 250)
    for t in res:
        t["half"] = t.entry_time.dt.year.astype(str) + np.where(t.entry_time.dt.month <= 6, "H1", "H2")
        top = t.r.nlargest(10).sum()
        lev = (1.25 / t.risk_pct)   # notional x equity at 1.25% risk
        print(f"floor {t.floor.iloc[0]:.1f} ATR: total {t.r.sum():+.1f}R, without top-10 trades {t.r.sum() - top:+.1f}R, "
              f"best {t.r.max():.1f}R, notional at 1.25% risk: median {lev.median():.1f}x, 99% {lev.quantile(.99):.1f}x equity")
        print("   by half:", t.groupby("half").r.sum().round(1).to_dict())
