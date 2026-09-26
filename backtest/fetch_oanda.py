"""Download OANDA XAU_USD 15m candles (the same broker feed as TradingView's
OANDA:XAUUSD) through OANDA's v20 REST API.

Needs a personal API token in the OANDA_API_TOKEN environment variable (free practice
account: Manage API Access). OANDA_ENV=live switches to a live account's endpoint.

  python3 fetch_oanda.py 2026-01-01            -> data/oanda_xauusd_15m_mid.csv and _bid.csv
"""
import os, sys, time
import pandas as pd, requests

HOST = {"practice": "https://api-fxpractice.oanda.com", "live": "https://api-fxtrade.oanda.com"}[os.environ.get("OANDA_ENV", "practice")]


def fetch(start, instrument="XAU_USD", granularity="M15"):
    token = os.environ["OANDA_API_TOKEN"]
    s = requests.Session(); s.headers["Authorization"] = f"Bearer {token}"
    rows, frm = [], pd.Timestamp(start, tz="UTC")
    while True:
        r = s.get(f"{HOST}/v3/instruments/{instrument}/candles",
                  params={"price": "MB", "granularity": granularity, "from": frm.isoformat(), "count": 5000}, timeout=60)
        r.raise_for_status()
        candles = [c for c in r.json()["candles"] if c["complete"]]
        if not candles: break
        for c in candles:
            rows.append({"time": c["time"], **{f"{k}_{side}": float(c[side][k]) for side in ("mid", "bid") for k in "ohlc"}})
        last = pd.Timestamp(candles[-1]["time"])
        if len(candles) < 4000: break
        frm = last + pd.Timedelta("1s"); time.sleep(0.2)
    df = pd.DataFrame(rows).drop_duplicates("time")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.set_index("time").sort_index()


if __name__ == "__main__":
    df = fetch(sys.argv[1] if len(sys.argv) > 1 else "2026-01-01")
    os.makedirs("data", exist_ok=True)
    for side in ("mid", "bid"):
        out = df[[f"{k}_{side}" for k in "ohlc"]]; out.columns = ["open", "high", "low", "close"]
        out.to_csv(f"data/oanda_xauusd_15m_{side}.csv")
    print(len(df), "candles,", df.index[0], "->", df.index[-1])
