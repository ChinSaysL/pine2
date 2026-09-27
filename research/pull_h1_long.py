import sys
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5, pandas as pd
mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe", login=5056530776, server="MetaQuotes-Demo", timeout=60000)
for sym in sys.argv[1:]:
    mt5.symbol_select(sym, True)
    parts = []; cur = datetime(2004, 1, 1, tzinfo=timezone.utc); end = datetime(2020, 2, 1, tzinfo=timezone.utc)
    while cur < end:
        nxt = min(cur + timedelta(days=200), end)
        r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, cur, nxt)
        if r is not None and len(r): parts.append(pd.DataFrame(r))
        cur = nxt
    if not parts: print(sym, "none", flush=True); continue
    df = pd.concat(parts).drop_duplicates("time").sort_values("time")
    srv = pd.to_datetime(df.time, unit="s")
    df["utc"] = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    df = df.dropna(subset=["utc"])
    df[["utc", "open", "high", "low", "close", "tick_volume", "spread"]].to_csv(f"data/OLD_{sym}_H1.csv", index=False)
    print(sym, len(df), df.utc.iloc[0], df.utc.iloc[-1], "spread med", df.spread.median(), flush=True)
mt5.shutdown()
