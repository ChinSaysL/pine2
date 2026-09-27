"""Daily analogue of the breakout strategy, to study regimes over 20+ years.
Each day: trend = yesterday's close vs 50d SMA with a 0.75 daily-ATR band, on the trend's side of the 200d EMA.
Long if today's high breaks yesterday's high + 0.05 ATR (short mirror); exit at today's close; stop 1 ATR
(if the day's range reaches it, assume stopped - conservative).  R = pnl / (1 ATR), cost 0.02 ATR."""
import numpy as np, pandas as pd

def load_d1(sym):
    d = pd.read_csv(f"data/D1_{sym}.csv", parse_dates=["date"]).set_index("date")
    d = d[d.index.dayofweek < 5]
    return d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})

def analogue(d, band=0.75, stop=1.0):
    tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    sma = d.c.rolling(50).mean(); ema = d.c.ewm(span=200, adjust=False).mean()
    pc = d.c.shift(1)
    trend = np.where((pc > sma.shift(1) + band * atr) & (pc > ema.shift(1)), 1,
                     np.where((pc < sma.shift(1) - band * atr) & (pc < ema.shift(1)), -1, 0))
    ph, pl = d.h.shift(1), d.l.shift(1)
    r = pd.Series(np.nan, index=d.index)
    up = (trend == 1) & (d.h > ph + 0.05 * atr)
    e = np.maximum(d.o, ph + 0.05 * atr)
    stopped = d.l <= e - stop * atr
    r[up] = np.where(stopped[up], -stop, (d.c[up] - e[up]) / atr[up]) - 0.02
    dn = (trend == -1) & (d.l < pl - 0.05 * atr)
    e2 = np.minimum(d.o, pl - 0.05 * atr)
    stopped2 = d.h >= e2 + stop * atr
    r[dn] = np.where(stopped2[dn], -stop, (e2[dn] - d.c[dn]) / atr[dn]) - 0.02
    r[:220] = np.nan
    return r

def regime(r, days=60, min_trades=5):
    """BAD if the analogue's R over the previous `days` calendar days < 0 with >= min_trades (known before today)."""
    s = r.fillna(0).rolling(f"{days}D").sum().shift(1)
    n = r.notna().astype(int).rolling(f"{days}D").sum().shift(1)
    return (n >= min_trades) & (s < 0)
