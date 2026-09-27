"""Post-earnings / news-shock drift on FTMO US stock CFDs (daily bars). Rules fixed in advance.
Event day t: opening gap |open_t / close_t-1 - 1| >= k x ATR% (ATR14 up to t-1) AND volume_t >= 2 x its 20-day mean.
Confirmation (optional): day t closes in the gap's direction (close_t beyond open_t).
Trade: enter at open_t+1 in the gap direction, stop 2 x ATR(t) from entry, exit at the open after N trading days
(stop checked on daily high/low; a gap through the stop fills at the open). Control: same events, opposite side.
Costs: 2 x median spread + 0.02% slippage per side, financing 7.7%/yr per calendar day held (FTMO swap).
FTMO stock leverage 1:3.3 -> position notional at 1.25% risk reported. Periods: dev start..2022, hold 2023-2026."""
import warnings; warnings.filterwarnings("ignore")
import glob, itertools, os
from multiprocessing import Pool
import numpy as np, pandas as pd

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"
META = pd.read_csv(f"{DATA}\\STK_meta.csv").set_index("sym")


def trades(sym, k=2.5, N=5, confirm=True, side=1):
    d = pd.read_csv(f"{DATA}\\STK_{sym}_D1.csv", parse_dates=["date"])
    o, h, l, c, v = d.open.values, d.high.values, d.low.values, d.close.values, d.tick_volume.values.astype(float)
    tr = np.maximum(d.high - d.low, np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().values
    vavg = pd.Series(v).rolling(20).mean().shift(1).values
    spread = 2 * META.loc[sym, "spread_med"] * META.loc[sym, "point"]
    out = []; t = 21
    while t < len(d) - N - 2:
        gap = o[t] / c[t - 1] - 1
        atrp = atr[t - 1] / c[t - 1]
        if abs(gap) >= k * atrp and v[t] >= 2 * vavg[t] and (not confirm or np.sign(c[t] - o[t]) == np.sign(gap)):
            dr = int(np.sign(gap)) * side
            i0 = t + 1; e = o[i0]; dist = 2 * atr[t]; st = e - dr * dist
            px = None; j = i0
            for j in range(i0, i0 + N):
                if j > i0 and ((dr == 1 and o[j] <= st) or (dr == -1 and o[j] >= st)): px = o[j]; break
                if (dr == 1 and l[j] <= st) or (dr == -1 and h[j] >= st): px = st; break
            if px is None: j = i0 + N; px = o[j]
            days = (d.date.iat[j] - d.date.iat[i0]).days
            cost = spread + 0.0004 * e + days * 0.077 / 365 * e
            out.append(dict(entry_time=d.date.iat[i0], exit_time=d.date.iat[j], sym=sym, r=((px - e) * dr - cost) / dist,
                            notional=0.0125 / (dist / e)))
            t = j + 1; continue
        t += 1
    return pd.DataFrame(out)


SYMS = list(META.index)
VARS = {f"k{k} N{N} {'confirm' if cf else 'no-confirm'}": dict(k=k, N=N, confirm=cf) for k in (2.0, 2.5, 3.0) for N in (5, 10) for cf in (True, False)}
VARS["CONTROL: opposite side (k2.5 N5 confirm)"] = dict(k=2.5, N=5, confirm=True, side=-1)


def job(name):
    t = pd.concat([trades(s, **VARS[name]) for s in SYMS]); t["name"] = name
    return t


if __name__ == "__main__":
    with Pool(14) as p:
        res = p.map(job, list(VARS))
    rows = []; allt = pd.concat(res); allt.to_pickle("pead_trades.pkl")
    for name, t in allt.groupby("name", sort=False):
        row = {"variant": name}
        for p_, a, b in [("dev ..2022", "2000-01-01", "2023-01-01"), ("hold 2023-26", "2023-01-01", "2027-01-01")]:
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            pf = x.r[x.r > 0].sum() / max(-x.r[x.r < 0].sum(), 1e-9)
            row[p_] = f"{x.r.sum():+6.1f}R n={len(x):4d} PF={pf:4.2f} win={100 * (x.r > 0).mean():3.0f}%"
        yr = t.groupby(t.entry_time.dt.year).r.sum()
        row["years +"] = f"{(yr > 0).sum()}/{len(yr)}"
        row["notional x eq (med)"] = round(t.notional.median(), 2)
        rows.append(row)
    pd.set_option("display.width", 260)
    print(pd.DataFrame(rows).to_string(index=False))
