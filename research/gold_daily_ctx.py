"""Daily context for the 2026-10-01 gold entry: how close was it to the ADX / EMA separation filters?"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    raise SystemExit(f"init failed {mt5.last_error()}")
mt5.symbol_select("XAUUSD", True)
r = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 0, 400)
mt5.shutdown()
d = pd.DataFrame(r)
srv = pd.to_datetime(d.time, unit="s")
ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
d["utc"] = ny.dt.tz_convert("UTC")
d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})
d["avg50"] = d.c.rolling(50).mean()
d["ema200"] = d.c.ewm(span=200, adjust=False).mean()

# Wilder ADX(14) on daily
up = d.h.diff(); dn = -d.l.diff()
plus = np.where((up > dn) & (up > 0), up, 0.0)
minus = np.where((dn > up) & (dn > 0), dn, 0.0)
tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
def wilder(s, n=14):
    return s.ewm(alpha=1 / n, adjust=False).mean()
atr = wilder(tr)
pdi = 100 * wilder(pd.Series(plus, index=d.index)) / atr
mdi = 100 * wilder(pd.Series(minus, index=d.index)) / atr
dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
d["adx"] = wilder(dx)

k = d.index[d.utc <= pd.Timestamp("2026-10-01 03:00", tz="UTC")][-1]
c = d.c[k]
print(f"daily bar {d.utc[k]:%Y-%m-%d}  close {c:.2f}")
print(f"  50-day average {d.avg50[k]:.2f}  -> distance {(c - d.avg50[k]) / d.avg50[k] * 100:+.2f}%   (neutral band = 1.00%)")
print(f"  200-day EMA    {d.ema200[k]:.2f}  -> separation {(c - d.ema200[k]) / d.ema200[k] * 100:+.2f}%  (InpEmaSepPct = 0 -> just the right side)")
print(f"  ADX(14)        {d.adx[k]:.1f}      (InpAdxMin = 0 = off; would need >= 20 to filter)")
print(f"  yesterday's close {d.c[k-1]:.2f}, previous-close used for the sell side: price below the 50-day avg = {(c < d.avg50[k])}")
print()
print("last 6 daily bars")
print(d.tail(6)[["utc", "o", "h", "l", "c", "avg50", "ema200", "adx"]].round(2).to_string(index=False))
print()
print("ADX over the last 20 days:", d.adx.tail(20).round(1).tolist())
print("50-day distance over the last 20 days (%):", ((d.c - d.avg50) / d.avg50 * 100).tail(20).round(2).tolist())
