"""Pull FTMO XAUUSD bars from the local MT5 terminal into research/data/*.csv (times in UTC)."""
import sys
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import pandas as pd

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
OUT = r"c:\Users\Abdo\Downloads\pine2\research\data"
SERVER_MINUS_UTC_WINTER = 2   # FTMO server = NY+7 -> UTC+2 winter / UTC+3 summer

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    sys.exit(f"init failed {mt5.last_error()}")
print(mt5.account_info().server, mt5.symbol_info(SYMBOL).spread, mt5.symbol_info(SYMBOL).point)
mt5.symbol_select(SYMBOL, True)
for name, tf in [("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1), ("D1", mt5.TIMEFRAME_D1)]:
    parts = []
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 28, tzinfo=timezone.utc)
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=180), end)
        r = mt5.copy_rates_range(SYMBOL, tf, cur, nxt)
        if r is not None and len(r):
            parts.append(pd.DataFrame(r))
        cur = nxt
    df = pd.concat(parts).drop_duplicates("time").sort_values("time")
    # MT5 'time' is server wall-clock as epoch; convert: server = NY + 7h
    srv = pd.to_datetime(df.time, unit="s")
    ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df["utc"] = ny.dt.tz_convert("UTC")
    df = df.dropna(subset=["utc"])
    df[["utc", "open", "high", "low", "close", "tick_volume", "spread"]].to_csv(f"{OUT}\{SYMBOL}_{name}.csv", index=False)
    print(name, len(df), df.utc.iloc[0], df.utc.iloc[-1], "median spread pts", df.spread.median())
mt5.shutdown()
