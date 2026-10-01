"""What are the latest Nasdaq trades on the account this terminal is logged into?
Read-only: account info + the last deals, plus a fresh M5 pull (last N bars, more reliable than a date range)."""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

OUT = r"c:\Users\Abdo\Downloads\pine2\research\data"
if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    raise SystemExit(f"init failed {mt5.last_error()}")
a = mt5.account_info()
print(f"account {a.login} {a.server} balance {a.balance} equity {a.equity} company {a.company}")

mt5.symbol_select("US100.cash", True)
from_dt = datetime(2026, 9, 20, tzinfo=timezone.utc)
to_dt = datetime(2026, 10, 2, tzinfo=timezone.utc)
deals = mt5.history_deals_get(from_dt, to_dt)
rows = []
for d in (deals or []):
    rows.append(dict(time=pd.to_datetime(d.time, unit="s"), symbol=d.symbol, type=d.type, entry=d.entry,
                     volume=d.volume, price=d.price, profit=d.profit, comm=d.commission, swap=d.swap,
                     magic=d.magic, comment=d.comment, position=d.position_id))
h = pd.DataFrame(rows)
if len(h):
    ny = h.time.dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    h["ny"] = ny.dt.strftime("%m-%d %H:%M")
    print("\n=== last 20 deals (NY time)")
    print(h.tail(20)[["ny", "symbol", "type", "entry", "volume", "price", "profit", "comm", "swap", "magic", "comment"]].to_string(index=False))

for name, tf, n in [("M5", mt5.TIMEFRAME_M5, 4000), ("M15", mt5.TIMEFRAME_M15, 2000)]:
    r = mt5.copy_rates_from_pos("US100.cash", tf, 0, n)
    if r is None or not len(r):
        print(name, "no data", mt5.last_error()); continue
    df = pd.DataFrame(r)
    srv = pd.to_datetime(df.time, unit="s")
    ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df["utc"] = ny.dt.tz_convert("UTC")
    df = df.dropna(subset=["utc"])[["utc", "open", "high", "low", "close", "tick_volume", "spread"]]
    df.to_csv(f"{OUT}\\FT_US100.cash_{name}_recent.csv", index=False)
    print(name, len(df), df.utc.iloc[0], "->", df.utc.iloc[-1])
mt5.shutdown()

