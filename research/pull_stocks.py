import sys
from datetime import datetime, timezone
import MetaTrader5 as mt5, pandas as pd
US = "AAPL AMZN BABA BAC GOOG MSFT NFLX NVDA PFE RACE T TSLA V WMT ZM META GE BA RTX LMT PLTR AMD INTC QCOM AVGO CSCO JNJ MCD SBUX KO MSTR GME NKE CVX FDX JPM DIS GM IBM ARM SNOW ASML AZN BRK.B XOM".split()
mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
assert mt5.account_info().server == "FTMO-Demo"
meta = []
for s in US:
    mt5.symbol_select(s, True); i = mt5.symbol_info(s)
    r = mt5.copy_rates_range(s, mt5.TIMEFRAME_D1, datetime(2010, 1, 1, tzinfo=timezone.utc), datetime(2026, 9, 28, tzinfo=timezone.utc))
    if r is None or len(r) < 300: print(s, "short/no data"); continue
    d = pd.DataFrame(r); d["date"] = pd.to_datetime(d.time, unit="s").dt.date
    d[["date", "open", "high", "low", "close", "tick_volume", "spread"]].to_csv(f"data/STK_{s}_D1.csv", index=False)
    meta.append(dict(sym=s, bars=len(d), first=d.date.iloc[0], point=i.point, spread_med=d.spread[d.spread > 0].median(), swap_long=i.swap_long, swap_short=i.swap_short, swap_mode=i.swap_mode))
mt5.shutdown()
m = pd.DataFrame(meta); m.to_csv("data/STK_meta.csv", index=False)
print(len(m), "stocks;", m[["sym", "bars", "first", "spread_med"]].to_string(index=False))
