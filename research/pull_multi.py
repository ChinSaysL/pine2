import sys
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import pandas as pd
OUT = r"c:\Users\Abdo\Downloads\pine2\research\data"
SYMS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","EURAUD",
        "CADJPY","CHFJPY","EURCHF","GBPAUD","AUDNZD","EURCAD","GBPCAD","NZDJPY",
        "US500","US30","USTEC","DE40","UK100","JPN225","FRA40","EUSTX50","AUS200","HK50","XPTUSD","XPDUSD","XAGUSD"]
mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe", login=5056530776, server="MetaQuotes-Demo", timeout=60000)
rows = []
for sym in SYMS:
    mt5.symbol_select(sym, True)
    parts = []; cur = datetime(2020, 1, 1, tzinfo=timezone.utc); end = datetime(2026, 9, 28, tzinfo=timezone.utc)
    while cur < end:
        nxt = min(cur + timedelta(days=150), end)
        r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, cur, nxt)
        if r is not None and len(r): parts.append(pd.DataFrame(r))
        cur = nxt
    if not parts:
        print(sym, "NO DATA"); continue
    df = pd.concat(parts).drop_duplicates("time").sort_values("time")
    srv = pd.to_datetime(df.time, unit="s")
    df["utc"] = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    df = df.dropna(subset=["utc"])
    df[["utc","open","high","low","close","tick_volume","spread"]].to_csv(f"{OUT}\XX_{sym}_H1.csv", index=False)
    i = mt5.symbol_info(sym)
    rows.append(dict(sym=sym, bars=len(df), first=df.utc.iloc[0].date(), point=i.point, spread_med=df.spread.median(),
                     contract=i.trade_contract_size, cur=i.currency_profit))
mt5.shutdown()
m = pd.DataFrame(rows); m.to_csv(f"{OUT}\XX_meta.csv", index=False); print(m.to_string(index=False))
