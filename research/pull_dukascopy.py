"""Nasdaq 100 minute candles from Dukascopy's public datafeed (BID), 2018-01..2022-06 -> data/DK_NDX_M1.csv (UTC)."""
import urllib.request, lzma, struct, time, sys
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

def day(d):
    path = f"USATECHIDXUSD/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
    for attempt in range(8):
        try:
            req = urllib.request.Request("https://datafeed.dukascopy.com/datafeed/" + path, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            raw = urllib.request.urlopen(req, timeout=40).read()
            if not raw: return []
            data = lzma.decompress(raw); base = pd.Timestamp(d, tz="UTC")
            rows = []
            for i in range(len(data) // 24):
                t, o, c, l, h, v = struct.unpack(">iiiiif", data[i * 24:(i + 1) * 24])
                if v > 0: rows.append((base + pd.Timedelta(seconds=t), o / 1000, h / 1000, l / 1000, c / 1000, v))
            return rows
        except Exception:
            time.sleep(3 + 3 * attempt)
    print("FAILED", d.date(), flush=True); return []

days = [d for d in pd.date_range("2018-01-01", "2022-06-30") if d.weekday() < 5]
out = []
with ThreadPoolExecutor(8) as ex:
    for k, rows in enumerate(ex.map(day, days)):
        out += rows
        if k % 100 == 0: print(k, len(days), len(out), flush=True)
df = pd.DataFrame(out, columns=["utc", "open", "high", "low", "close", "volume"]).sort_values("utc")
df.to_csv("data/DK_NDX_M1.csv", index=False)
print("done", len(df), df.utc.iloc[0], df.utc.iloc[-1])
