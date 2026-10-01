import re
import glob
import os

# 1. the MT5-generated report for the control run (authoritative deal list)
base = r"C:\Users\Abdo\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Tester"
for f in sorted(glob.glob(os.path.join(base, "CC_ctrl2020*"))):
    if not f.endswith(".htm"):
        continue
    txt = open(f, encoding="utf-16", errors="ignore").read()
    if len(txt) < 100:
        txt = open(f, encoding="utf-8", errors="ignore").read()
    deals = re.findall(r">\s*(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s*<", txt)
    dates = sorted(set(deals))
    print(os.path.basename(f), f"{os.path.getsize(f)/1e6:.2f} MB", "deal timestamps:", len(deals),
          "first", dates[0] if dates else "-", "last", dates[-1] if dates else "-")

# 2. the EA's own journal in the tester agent log
for ag in sorted(glob.glob(r"C:\Users\Abdo\AppData\Roaming\MetaQuotes\Tester\D0E8209F77C8CF37AD8BF550E51FF075\Agent-127.0.0.1-*\logs\20261001.log")):
    lines = open(ag, encoding="utf-16", errors="ignore").read().splitlines()
    if len(lines) < 50:
        lines = open(ag, encoding="utf-8", errors="ignore").read().splitlines()
    ent = [l for l in lines if "[ENTRY]" in l]
    if not ent:
        continue
    times = [re.search(r"\)\s+(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})", l) for l in ent]
    times = sorted(t.group(1) for t in times if t)
    print(os.path.basename(ag), "ENTRY lines:", len(ent), "first", times[0] if times else "-", "last", times[-1] if times else "-")
