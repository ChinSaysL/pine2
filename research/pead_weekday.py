"""Post-earnings drift, weekday-only: enter next open after a confirmed event (gap >= 2.5 ATR%, 2x volume, close in gap
direction), hold at most N trading days but ALWAYS flat at Friday's close (never over a weekend); skip entries on Fridays.
Stop 2 ATR. Costs: 2 x spread + 0.02%/side + 7.7%/yr financing per night held."""
import warnings; warnings.filterwarnings("ignore")
from multiprocessing import Pool
import numpy as np, pandas as pd
DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
META = pd.read_csv(f"{DATA}\STK_meta.csv").set_index("sym")

def trades(sym, k=2.5, N=4, side=1):
    d = pd.read_csv(f"{DATA}\STK_{sym}_D1.csv", parse_dates=["date"])
    o, h, l, c, v = d.open.values, d.high.values, d.low.values, d.close.values, d.tick_volume.values.astype(float)
    tr = np.maximum(d.high - d.low, np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().values
    vavg = pd.Series(v).rolling(20).mean().shift(1).values
    wd = d.date.dt.weekday.values
    sp = 2 * META.loc[sym, "spread_med"] * META.loc[sym, "point"]
    out = []; t = 21
    while t < len(d) - N - 2:
        gap = o[t] / c[t - 1] - 1
        if abs(gap) >= k * atr[t - 1] / c[t - 1] and v[t] >= 2 * vavg[t] and np.sign(c[t] - o[t]) == np.sign(gap) and wd[t + 1] != 4:
            dr = int(np.sign(gap)) * side; i0 = t + 1; e = o[i0]; dist = 2 * atr[t]; st = e - dr * dist; px = None
            j = i0
            while True:
                if j > i0 and ((dr == 1 and o[j] <= st) or (dr == -1 and o[j] >= st)): px = o[j]; break
                if (dr == 1 and l[j] <= st) or (dr == -1 and h[j] >= st): px = st; break
                if wd[j] == 4 or j - i0 + 1 >= N or j + 1 >= len(d) or wd[j + 1] <= wd[j]: px = c[j]; break   # Friday / N days / week end
                j += 1
            nights = j - i0
            cost = sp + 0.0004 * e + nights * 0.077 / 365 * e
            out.append(dict(entry_time=d.date.iat[i0], r=((px - e) * dr - cost) / dist, sym=sym))
            t = j + 1; continue
        t += 1
    return pd.DataFrame(out)

def job(a):
    k, N, side = a
    t = pd.concat([trades(s, k, N, side) for s in META.index]); t["name"] = f"k{k} max{N}d{' CONTROL' if side == -1 else ''}"; return t

if __name__ == "__main__":
    grid = [(k, N, 1) for k in (2.0, 2.5, 3.0) for N in (2, 4)] + [(2.5, 4, -1)]
    with Pool(14) as p: res = p.map(job, grid)
    for t in res:
        s = []
        for a, b in (("2000", "2023"), ("2023", "2027")):
            x = t[(t.entry_time >= a) & (t.entry_time < b)]; pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            s.append(f"{x.r.sum():+6.1f}R n={len(x):3d} PF={pf:4.2f}")
        yr = t.groupby(t.entry_time.dt.year).r.sum()
        print(f"{t.name.iat[0]:18s} dev..2022: {s[0]} | hold 2023-26: {s[1]} | years+ {(yr > 0).sum()}/{len(yr)}")
