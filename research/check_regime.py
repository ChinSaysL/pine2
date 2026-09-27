import pandas as pd, numpy as np
from regime import load_mt5, paper_trades, regime_flag
df = load_mt5("H1")
p = paper_trades(df)
bad = regime_flag(df, p)
df["bad"] = bad
p["year"] = p.exit_time.dt.year
print("paper trades", len(p), "R by year"); print(p.groupby("year").r.agg(["count", "sum"]).round(1))
ea = pd.read_csv(r"C:\Users\Abdo\AppData\Local\Temp\claude\c--Users-Abdo-Downloads-pine2\477288ce-7536-44c5-bc98-9eeb2dc7aa6e\scratchpad\paper_p_regon.csv", sep=";")
ea["t"] = pd.to_datetime(ea.exit_ny).dt.tz_localize("America/New_York", ambiguous="NaT").dt.tz_convert("UTC")
ea["year"] = ea.t.dt.year
print("EA paper R by year"); print(ea.groupby("year").r.agg(["count", "sum"]).round(1))
m = df.groupby(df.time.dt.to_period("Q")).bad.mean().round(2)
print("share of hours in BAD regime by quarter"); print(m.to_string())
