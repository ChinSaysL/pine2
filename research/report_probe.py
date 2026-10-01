import re
import sys
import glob
import os

base = r"C:\Users\Abdo\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Tester"
for pat in ["GTBPen_cc_*.htm", "GoldBreakout_bm_halfrisk.htm"]:
    for f in sorted(glob.glob(os.path.join(base, pat))):
        if "-" in os.path.basename(f):
            continue
        txt = open(f, encoding="utf-16", errors="ignore").read()
        if len(txt) < 100:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        dates = re.findall(r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2})", txt)
        trades = re.findall(r"position #\d+|deal #\d+", txt)
        print(f"{os.path.basename(f):42} {os.path.getsize(f)/1e6:6.2f} MB  date-stamps {len(dates):6d}  "
              f"first {min(dates) if dates else '-'}  last {max(dates) if dates else '-'}")
        # try to find the tester header line with the range
        for m in re.finditer(r"(Interval|from|to)[^<]{0,40}\d{4}\.\d{2}\.\d{2}[^<]{0,40}", txt):
            print("    hdr:", m.group(0)[:110].replace("&nbsp;", " "))
            break
