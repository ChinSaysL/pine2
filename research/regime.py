"""Load MT5 bars and rebuild the live EA's trend strategy + its paper-trading regime flag in Python."""
import numpy as np
import pandas as pd
from concepts import prep
from pyramid import simulate_pyr

DATA = r"c:\Users\Abdo\Downloads\pine2\research\data"


def load_mt5(tf="H1", symbol="XAUUSD"):
    d = pd.read_csv(f"{DATA}\{symbol}_{tf}.csv")
    d = d.rename(columns={"utc": "time", "open": "o", "high": "h", "low": "l", "close": "c"})
    d["time"] = pd.to_datetime(d.time, utc=True)
    return prep(d)


def trend_array(df, n=50, band=1.0, ema_len=200):
    """EA trend: yesterday's close vs 50d SMA with a neutral band, and only on the trend's side of the 200d EMA."""
    closes = df.groupby("tday").c.last()
    sma = closes.rolling(n).mean()
    ema = closes.ewm(span=ema_len, adjust=False).mean()
    raw = np.where(closes > sma * (1 + band / 100), 1, np.where(closes < sma * (1 - band / 100), -1, 0))
    ok = np.where(raw == 1, closes > ema, np.where(raw == -1, closes < ema, False))
    tr = pd.Series(np.where(ok & (np.arange(len(closes)) >= ema_len // 2), raw, 0), index=closes.index).shift(1)
    return df.tday.map(tr).fillna(0).values


def paper_trades(df):
    """All-session paper trades of the trend strategy (every unit counted, like the EA's paper engine)."""
    return simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=trend_array(df), add_at=(1.0,),
                        flat_ny=16 + 50 / 60)


def regime_flag(df, paper, days=60, min_trades=5):
    """Per bar: True = BAD regime (paper R of trades closed in the last `days` days < 0 with >= min_trades)."""
    ex = paper.exit_time.values.astype("datetime64[ns]")
    r = paper.r.values
    order = np.argsort(ex)
    ex, r = ex[order], r[order]
    cum = np.concatenate([[0.0], np.cumsum(r)])
    t = df.time.values.astype("datetime64[ns]")
    hi = np.searchsorted(ex, t, side="left")                 # trades closed strictly before this bar
    lo = np.searchsorted(ex, t - np.timedelta64(days, "D"), side="left")
    n = hi - lo
    s = cum[hi] - cum[lo]
    return (n >= min_trades) & (s < 0)
