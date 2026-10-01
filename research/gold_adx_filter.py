"""Would a daily-ADX filter (InpAdxMin) have helped the gold EA? Uses the 2010-2026 real-EA export
and the daily ADX(14) the EA reads (Wilder, daily bars)."""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    raise SystemExit(f"init failed {mt5.last_error()}")
mt5.symbol_select("XAUUSD", True)
r = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 0, 6000)
mt5.shutdown()
d = pd.DataFrame(r)
srv = pd.to_datetime(d.time, unit="s")
ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
d["utc"] = ny.dt.tz_convert("UTC")
d = d.rename(columns={"high": "h", "low": "l", "close": "c"})
up, dn = d.h.diff(), -d.l.diff()
plus = np.where((up > dn) & (up > 0), up, 0.0)
minus = np.where((dn > up) & (dn > 0), dn, 0.0)
tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
w = lambda s: s.ewm(alpha=1 / 14, adjust=False).mean()
atr = w(tr)
pdi = 100 * w(pd.Series(plus, index=d.index)) / atr
mdi = 100 * w(pd.Series(minus, index=d.index)) / atr
d["adx"] = w(100 * (pdi - mdi).abs() / (pdi + mdi))
print("daily data", d.utc.iloc[0].date(), "->", d.utc.iloc[-1].date(), len(d), "bars")

t = pd.read_csv(r"c:\Users\Abdo\Downloads\pine2\research\mt5_bm_halfrisk.csv", sep=";")
t["et_ny"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
t = t.dropna(subset=["et_ny"])
t["et"] = t.et_ny.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
t = t.dropna(subset=["et"])
# the daily bar the EA would have seen: the last one that closed before the entry
didx = np.searchsorted(d.utc.values, t.et.values, side="right") - 1
t = t[didx >= 0]
t["adx"] = d.adx.values[didx[didx >= 0]]
print(f"trades with a daily ADX: {len(t)}  {t.et.min():%Y-%m-%d} .. {t.et.max():%Y-%m-%d}")

bands = [(0, 15), (15, 18), (18, 20), (20, 22), (22, 25), (25, 100)]
print("\nR by the daily ADX at entry (the EA's InpAdxMin would skip everything below the threshold):")
rows = []
for lo, hi in bands:
    s = t[(t.adx >= lo) & (t.adx < hi)]
    if not len(s):
        continue
    rows.append(dict(ADX=f"{lo}-{hi}", n=len(s), R=round(s.r.sum(), 1), per_trade=round(s.r.mean(), 3),
                     PF=round(s.r[s.r > 0].sum() / max(-s.r[s.r < 0].sum(), 1e-9), 2), win=f"{(s.r > 0).mean():.0%}"))
print(pd.DataFrame(rows).to_string(index=False))
print("\ncumulative effect of a filter 'only take trades with ADX >= X':")
for x in (0, 15, 18, 19, 20, 22, 25):
    keep = t[t.adx >= x]; drop = t[t.adx < x]
    print(f"  ADX >= {x:2d}: keep {len(keep):4d} trades {keep.r.sum():+7.1f}R   dropped {len(drop):4d} trades {drop.r.sum():+7.1f}R")
print("\ntoday's trade (2026-10-01) ADX:", float(d.adx.iloc[-1]), float(d.adx.iloc[-2]))
