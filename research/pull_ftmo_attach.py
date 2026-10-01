"""Pull FTMO bars by attaching to the user's running (logged-in) MT5 - no restart, no login change."""
import sys
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5, pandas as pd
OUT = r"c:\Users\Abdo\Downloads\pine2\research\data"
TF = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"): sys.exit(str(mt5.last_error()))
assert mt5.account_info().server == "FTMO-Demo"
tfs = sys.argv[1].split(","); syms = sys.argv[2:]
rows = []
for sym in syms:
    mt5.symbol_select(sym, True); info = mt5.symbol_info(sym)
    for tf in tfs:
        parts = []; cur = datetime(2015, 1, 1, tzinfo=timezone.utc); end = datetime(2026, 9, 28, tzinfo=timezone.utc)
        while cur < end:
            nxt = min(cur + timedelta(days=60), end)
            r = mt5.copy_rates_range(sym, TF[tf], cur, nxt)
            if r is not None and len(r): parts.append(pd.DataFrame(r))
            cur = nxt
        if not parts: print(sym, tf, "NO DATA", flush=True); continue
        df = pd.concat(parts).drop_duplicates("time").sort_values("time")
        srv = pd.to_datetime(df.time, unit="s")
        df["utc"] = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        df = df.dropna(subset=["utc"])
        df[["utc", "open", "high", "low", "close", "tick_volume", "spread"]].to_csv(f"{OUT}\FT_{sym}_{tf}.csv", index=False)
        rows.append(dict(sym=sym, tf=tf, bars=len(df), first=df.utc.iloc[0], last=df.utc.iloc[-1], spread_med=df.spread.median(),
                         point=info.point, contract=info.trade_contract_size, cur=info.currency_profit))
        print(rows[-1], flush=True)
mt5.shutdown()
m = pd.DataFrame(rows)
old = pd.read_csv(f"{OUT}\FT_meta.csv") if __import__("os").path.exists(f"{OUT}\FT_meta.csv") else pd.DataFrame()
pd.concat([old, m]).drop_duplicates(["sym", "tf"], keep="last").to_csv(f"{OUT}\FT_meta.csv", index=False)
