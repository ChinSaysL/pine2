"""Hourly klines from Binance's public API (no key) -> data/BN_<SYM>_H1.csv, UTC."""
import sys, time, json, urllib.request
import pandas as pd
def fetch(sym, start_ms):
    rows = []; t = start_ms
    while True:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&startTime={t}&limit=1000"
        k = json.loads(urllib.request.urlopen(url, timeout=30).read())
        if not k: break
        rows += k; t = k[-1][0] + 3600_000
        if len(k) < 1000: break
        time.sleep(0.15)
    d = pd.DataFrame(rows).iloc[:, :6]; d.columns = ["t", "open", "high", "low", "close", "volume"]
    d["utc"] = pd.to_datetime(d.t, unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]: d[c] = d[c].astype(float)
    return d[["utc", "open", "high", "low", "close", "volume"]]
for s in sys.argv[1:]:
    d = fetch(s, int(pd.Timestamp("2018-01-01", tz="UTC").timestamp() * 1000))
    d.to_csv(f"data/BN_{s}_H1.csv", index=False)
    print(s, len(d), d.utc.iloc[0], d.utc.iloc[-1], flush=True)
