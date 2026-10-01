"""Two checks:
1) how much history the rig tester actually had (which years did the A/B cover),
2) DST sanity: does the FTMO US100.cash M5 data map the cash session to 09:30 New York all year round?
   (the repo converts MT5 server time with a constant 7h offset; if the server and New York switch DST at
   different dates, the derived session start would drift by an hour in those windows)."""
import pandas as pd

D = r"c:\Users\Abdo\Downloads\pine2\research\data"
d = pd.concat([pd.read_csv(f"{D}\\FT_US100.cash_M5.csv"), pd.read_csv(f"{D}\\FT_US100.cash_M5_recent.csv")])
d = d.drop_duplicates(subset=["utc"]).sort_values("utc")
d["utc"] = pd.to_datetime(d.utc, utc=True)
ny = d.utc.dt.tz_convert("America/New_York")
d["date"], d["hm"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute
print("data", d.utc.min(), "->", d.utc.max())

# first bar of each NY date
first = d.groupby("date").hm.min()
print("\n1) session start (minutes past NY midnight) - 570 = 09:30 New York")
print(first.value_counts().head(8).to_string())
bad = first[first != 570]
print(f"   dates whose first bar is NOT 09:30 NY: {len(bad)} of {len(first)}")
print("   by month of the bad ones:", bad.index.to_series().groupby(pd.to_datetime(bad.index).to_period("M")).size().to_dict())

# a session is only usable when the first bar is exactly 09:30
sessions = {k: x for k, x in d[(d.hm >= 570) & (d.hm < 960)].groupby("date") if x.hm.iat[0] == 570 and len(x) >= 70}
s = pd.Series(1, index=pd.to_datetime(list(sessions)))
cnt = s.groupby(s.index.to_period("M")).size()
print("\n   usable sessions per year:", cnt.groupby(cnt.index.year).sum().to_dict())
print("   months with fewer than 15 sessions:")
print(cnt[cnt < 15].to_string() if (cnt < 15).any() else "   (none)")

# DST windows: US switches 2nd Sun of March / 1st Sun of November; EET switches last Sun of March / October
print("\n2) around the DST switch windows (first bar NY time per day)")
for lo, hi in [("2026-03-05", "2026-04-02"), ("2026-10-22", "2026-11-05"), ("2025-03-05", "2025-04-02"), ("2025-10-22", "2025-11-05")]:
    sub = first[(first.index >= pd.Timestamp(lo).date()) & (first.index <= pd.Timestamp(hi).date())]
    if len(sub):
        print(f"   {lo}..{hi}: " + ", ".join(f"{k.strftime('%m-%d')}={v}" for k, v in sub.items()))
