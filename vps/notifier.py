#!/usr/bin/env python3
"""Gold Trend Breakout - Telegram notifier and watchdog.

* forwards every line of the EA's events.log to Telegram
* alerts when the EA heartbeat is stale during market hours, when MT5 is disconnected,
  when Algo Trading is off, when the MT5 service is not running, or when the gold EA
  is not on the H1 chart it is built for
* restarts gtb-mt5 / gtb-mt5-nq when their EA heartbeat stays stale (frozen terminal),
  at most once every RESTART_COOLDOWN_MIN minutes
* sends a daily summary shortly after the 17:00 New York close

Standard library only. Telegram credentials come from /etc/gtb/telegram.env:
    TELEGRAM_BOT_TOKEN=123:abc
    TELEGRAM_CHAT_ID=123456
Without them it only logs to the journal (journalctl -u gtb-notifier).
"""
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FILES = "/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
EVENTS = os.path.join(FILES, "events.log")
HEARTBEAT = os.path.join(FILES, "heartbeat.txt")
NQ_HEARTBEAT = os.path.join(FILES, "nasdaq_heartbeat.txt")
STATE = "/home/mt5/gtb/notifier_state.json"
ENV = "/etc/gtb/telegram.env"
NY = ZoneInfo("America/New_York")
STALE_MIN = 10
GOLD_PERIOD = os.environ.get("GTB_EXPECTED_PERIOD", "PERIOD_H1")  # the gold EA is built for H1
AUTO_RESTART = os.environ.get("GTB_AUTO_RESTART", "1") == "1"
RESTART_COOLDOWN_MIN = 30



def load_env(path):
    env = {}
    try:
        for line in open(path):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    except FileNotFoundError:
        pass
    return env


def send(text):
    env = load_env(ENV)
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    print(text, flush=True)
    if not token or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    for _ in range(3):
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15).read()
            return
        except Exception as e:  # network hiccup: retry, then give up on this message
            print(f"telegram error: {e}", flush=True)
            time.sleep(5)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"offset": 0, "alerts": {}, "summary_day": ""}


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"))
    os.replace(tmp, STATE)


def read_heartbeat(path=HEARTBEAT):
    hb = {}
    try:
        for line in open(path, encoding="latin-1"):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                hb[k] = v
        hb["_mtime"] = os.path.getmtime(path)
    except FileNotFoundError:
        pass
    return hb


def market_open(now_utc):
    """Gold CFD hours: Sunday 18:00 - Friday 17:00 New York, with a daily 17:00-18:00 break."""
    ny = now_utc.astimezone(NY)
    wd, h = ny.weekday(), ny.hour + ny.minute / 60   # Monday = 0
    if wd == 5 or (wd == 4 and h >= 17) or (wd == 6 and h < 18):
        return False
    return not (17 <= h < 18)


def service_active(name):
    return subprocess.run(["systemctl", "is-active", "--quiet", name]).returncode == 0


def restart_service(name):
    """Recover a terminal that is up as a service but whose EA stopped talking."""
    try:
        r = subprocess.run(["systemctl", "restart", name], capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception as e:
        print(f"restart {name} failed: {e}", flush=True)
        return False


def maybe_restart(st, key, service, age_min, why):
    """One recovery restart per cooldown window, announced on Telegram."""
    st.setdefault("restarts", {})
    last = st["restarts"].get(key, 0)
    if not AUTO_RESTART:
        return
    if time.time() - last < RESTART_COOLDOWN_MIN * 60:
        return
    st["restarts"][key] = time.time()
    ok = restart_service(service)
    send(f"🔄 {why} ({age_min:.0f} min) -> restarting {service}: {'started' if ok else 'FAILED, check the server'}")



def alert_once(st, key, active, text_on, text_off=None):
    """Send text_on when a problem starts, text_off when it clears."""
    was = st["alerts"].get(key, False)
    if active and not was:
        send(text_on)
    elif was and not active and text_off:
        send(text_off)
    st["alerts"][key] = active


def main():
    st = load_state()
    send("🟢 Gold bot notifier started")
    while True:
        now = datetime.now(timezone.utc)
        # 1) forward new EA events
        try:
            size = os.path.getsize(EVENTS)
            if size < st["offset"]:
                st["offset"] = 0                      # log was rotated or recreated
            if size > st["offset"]:
                with open(EVENTS, "rb") as f:
                    f.seek(st["offset"])
                    chunk = f.read()
                st["offset"] += len(chunk)
                for line in chunk.decode("latin-1").splitlines():
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        _, kind, sym, msg = parts
                        icon = {"ENTRY": "📈", "ADD": "➕", "CLOSE": "📉", "EXIT": "🚪", "ERROR": "❌", "WARNING": "⚠️",
                                "STOP": "⛔", "TARGET": "🏁", "START": "▶️", "RESTORE": "🔄",
                                "FILL": "✅", "SKIP": "⏭️", "REGIME": "🧭"}.get(kind, "ℹ️")
                        send(f"{icon} {kind} {sym}: {msg}")
        except FileNotFoundError:
            pass

        # 2) watchdog
        hb = read_heartbeat()
        mt5_up = service_active("gtb-mt5")
        alert_once(st, "service", not mt5_up, "❌ MT5 service is not running (systemctl status gtb-mt5)",
                   "✅ MT5 service is running again")
        if market_open(now) and mt5_up:
            age = (time.time() - hb["_mtime"]) / 60 if "_mtime" in hb else 1e9
            if age > STALE_MIN:
                maybe_restart(st, "gold", "gtb-mt5", age, "❌ Gold EA heartbeat stale")
            alert_once(st, "stale", age > STALE_MIN, f"❌ No EA heartbeat for {age:.0f} min - EA not running or terminal frozen",
                       "✅ EA heartbeat is back")
            # the gold EA is built for H1: an M1/M15 chart silently changes the strategy
            period = hb.get("period", "")
            alert_once(st, "period", bool(period) and period != GOLD_PERIOD,
                       f"❌ The gold EA is running on {period} instead of {GOLD_PERIOD} - restart gtb-mt5 and check the chart",
                       "✅ The gold EA is back on the expected timeframe")

        # Nasdaq companion: its own MT5 service and heartbeat (written every 30 s, market open or not)
        if os.path.exists("/etc/systemd/system/gtb-mt5-nq.service"):
            nq_up = service_active("gtb-mt5-nq")
            alert_once(st, "nq_service", not nq_up, "❌ Nasdaq MT5 service is not running (systemctl status gtb-mt5-nq)",
                       "✅ Nasdaq MT5 service is running again")
            nq = read_heartbeat(NQ_HEARTBEAT)
            nq_age = (time.time() - nq["_mtime"]) / 60 if "_mtime" in nq else 1e9
            if nq_up and nq_age > STALE_MIN:
                maybe_restart(st, "nq", "gtb-mt5-nq", nq_age, "❌ Nasdaq EA heartbeat stale")
            alert_once(st, "nq_stale", nq_up and nq_age > STALE_MIN, f"❌ No Nasdaq EA heartbeat for {nq_age:.0f} min - EA not running or terminal frozen",
                       "✅ Nasdaq EA heartbeat is back")

            alert_once(st, "disconnected", hb.get("connected") == "0", "❌ MT5 is disconnected from the broker",
                       "✅ MT5 reconnected")
            algo_off = hb.get("terminal_trade_allowed") == "0" or hb.get("ea_trade_allowed") == "0"
            alert_once(st, "algo", algo_off, "❌ Algo Trading is OFF - the EA cannot trade", "✅ Algo Trading is on")
            alert_once(st, "account", hb.get("account_trade_allowed") == "0", "❌ The account does not allow trading",
                       "✅ Account trading allowed again")

        # 3) daily summary after the New York close
        ny = now.astimezone(NY)
        day = ny.strftime("%Y-%m-%d")
        if ny.hour == 17 and ny.minute >= 5 and ny.weekday() < 5 and st.get("summary_day") != day and hb:
            send(f"📊 Daily summary {day}\nbalance {hb.get('balance')}  equity {hb.get('equity')}\n"
                 f"today {hb.get('day_pl_pct')}%  total {hb.get('total_pl_pct')}% (initial {hb.get('initial_balance')})\n"
                 f"trading days {hb.get('trading_days')}  open positions {hb.get('positions')}  "
                 f"target reached {'yes' if hb.get('passed') == '1' else 'no'}")
            st["summary_day"] = day

        save_state(st)
        time.sleep(20)


if __name__ == "__main__":
    main()
