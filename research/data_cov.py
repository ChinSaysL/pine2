import glob
import pandas as pd
for f in sorted(glob.glob(r"c:\Users\Abdo\Downloads\pine2\research\data\XAUUSD_*.csv")):
    d = pd.read_csv(f, nrows=3)
    full = pd.read_csv(f)
    print(f.split("\\")[-1], len(full), list(full.columns)[:7])
    print("   ", full.iloc[0, 0], "->", full.iloc[-1, 0])
