"""Signal engine: a Python port of the indicator part of pinescsript.txt (SuperTrend AI
clustering, fakeout filter, reversal zones, WaveTrend trigger waves). compute(df) takes
15m OHLC with a UTC index and columns open, high, low, close."""
import numpy as np, pandas as pd, math

def rma(x, n):
    out = np.full(len(x), np.nan); s = None; buf = []
    for i, v in enumerate(x):
        if np.isnan(v): continue
        if s is None:
            buf.append(v)
            if len(buf) == n: s = np.mean(buf); out[i] = s
        else:
            s = (s * (n - 1) + v) / n; out[i] = s
    return out

def ema(x, n):
    a = 2 / (n + 1); out = np.full(len(x), np.nan); s = None; buf = []
    for i, v in enumerate(x):
        if np.isnan(v): continue
        if s is None:
            buf.append(v)
            if len(buf) == n: s = np.mean(buf); out[i] = s
        else:
            s = a * v + (1 - a) * s; out[i] = s
    return out

def pct_interp(a, p):
    a = sorted(a); n = len(a)
    if n == 0: return np.nan
    # Pine percentile_linear_interpolation
    pos = p / 100 * (n - 1); lo = int(math.floor(pos)); hi = min(lo + 1, n - 1)
    return a[lo] + (a[hi] - a[lo]) * (pos - lo)

def supersmoother(src, L):
    a1 = math.exp(-math.sqrt(2) * math.pi / L); b1 = 2 * a1 * math.cos(math.sqrt(2) * math.pi / L)
    c3 = -a1 * a1; c2 = b1; c1 = 1 - c2 - c3
    ss = np.full(len(src), np.nan)
    for i in range(len(src)):
        s1 = ss[i-1] if i >= 1 and not np.isnan(ss[i-1]) else (src[i-1] if i >= 1 else np.nan)
        s2 = ss[i-2] if i >= 2 and not np.isnan(ss[i-2]) else (src[i-2] if i >= 2 else np.nan)
        v = c1 * src[i] + c2 * s1 + c3 * s2
        ss[i] = v
    return ss

def dualpole(src, lb):
    om = -99 * math.pi / (70 * lb); al = math.exp(om); be = -al * al; ga = math.cos(om) * 2 * al; de = 1 - ga - be
    f = np.zeros(len(src))
    for i in range(len(src)):
        s = src[i]; sp = src[i-1] if i >= 1 and not np.isnan(src[i-1]) else s
        sa = 0.5 * (s + sp)
        f1 = f[i-1] if i >= 1 and not np.isnan(f[i-1]) else 0.0
        f2 = f[i-2] if i >= 2 and not np.isnan(f[i-2]) else 0.0
        f[i] = de * sa + ga * f1 + be * f2
    return f

def oscillator(close, lb):
    d = np.full(len(close), np.nan); d[2:] = close[2:] - close[:-2]
    s = pd.Series(d ** 2).rolling(50).sum().values
    qm = np.sqrt(np.nan_to_num(s / 50))
    nd = d / qm
    th = -1 + 2 / (1 + np.exp(-2 * nd))
    return dualpole(th, lb)

def gaussian(src, lookback, start):
    out = np.full(len(src), np.nan)
    for i in range(len(src)):
        cw = 0; cum = 0
        for j in range(0, 1 + start + 1):
            if i - j < 0: continue
            y = src[i - j]
            if np.isnan(y): continue
            w = math.exp(-j * j / (2 * lookback * lookback)); cw += y * w; cum += w
        out[i] = cw / cum if cum else np.nan
    return out

def compute(df, maxData=2500, sensitivity=5, atrLength=10, fakeout="Medium", filterOn=True):
    o, h, l, c = [df[k].values.astype(float) for k in ("open", "high", "low", "close")]
    N = len(c); hl2 = (h + l) / 2; hlc3 = (h + l + c) / 3
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]])))
    tr_true = tr.copy(); tr_true[0] = h[0] - l[0]
    atr = rma(tr_true, atrLength)
    minM = max(sensitivity - 4, 1); maxM = min(sensitivity, 26)
    factors = [minM + i * .5 for i in range(int((maxM - minM) / .5) + 1)]
    K = len(factors)
    up_ = np.full(K, hl2[0]); lo_ = np.full(K, hl2[0]); out_ = np.full(K, np.nan); perf = np.zeros(K); trend = np.zeros(K)
    den = ema(np.r_[np.nan, np.abs(np.diff(c))], 10)
    last = N - 1
    target = np.nan; perf_idx_v = np.nan; have_clusters = False; cl_f = None; cl_p = None
    upper = hl2[0]; lower = hl2[0]; os_ = 0
    OS = np.zeros(N, int); TS = np.full(N, np.nan); PI = np.full(N, np.nan); TF = np.full(N, np.nan)
    for i in range(N):
        a = atr[i]
        for k, f in enumerate(factors):
            upv = hl2[i] + a * f; dnv = hl2[i] - a * f
            trend[k] = 1 if c[i] > up_[k] else (0 if c[i] < lo_[k] else trend[k])
            cp = c[i-1] if i else np.nan
            up_[k] = min(upv, up_[k]) if (cp < up_[k]) else upv
            lo_[k] = max(dnv, lo_[k]) if (cp > lo_[k]) else dnv
            diff = 0 if (i == 0 or np.isnan(out_[k])) else np.sign(c[i-1] - out_[k])
            ch = 0 if i == 0 else c[i] - c[i-1]
            perf[k] += 2 / 11 * (ch * diff - perf[k])
            out_[k] = lo_[k] if trend[k] == 1 else up_[k]
        if last - i <= maxData:
            data = list(perf); cent = [pct_interp(data, 25), pct_interp(data, 50), pct_interp(data, 75)]
            for _ in range(251):
                fc = [[], [], []]; pc = [[], [], []]
                for j, v in enumerate(data):
                    ds = [abs(v - ce) if not np.isnan(ce) else np.nan for ce in cent]
                    mn = np.nanmin(ds); idx = ds.index(mn) if not np.isnan(mn) else 0
                    pc[idx].append(v); fc[idx].append(factors[j])
                nc = [np.mean(x) if x else np.nan for x in pc]
                if all(nc[q] == cent[q] for q in range(3)): break
                cent = nc
            cl_f, cl_p = fc, pc; have_clusters = True
        if have_clusters:
            tfv = np.mean(cl_f[2]) if cl_f[2] else np.nan
            target = tfv if not np.isnan(tfv) else target
            pv = np.mean(cl_p[2]) if cl_p[2] else 0.0
            perf_idx_v = max(pv, 0) / den[i] if not np.isnan(den[i]) else np.nan
        TF[i] = target; PI[i] = perf_idx_v
        upv = hl2[i] + a * target; dnv = hl2[i] - a * target
        cp = c[i-1] if i else np.nan
        upper = (min(upv, upper) if (cp < upper) else upv)
        lower = (max(dnv, lower) if (cp > lower) else dnv)
        if np.isnan(upper) or np.isnan(lower):
            upper = upv if np.isnan(upper) else upper; lower = dnv if np.isnan(lower) else lower
        os_ = 1 if c[i] > upper else (0 if c[i] < lower else os_)
        OS[i] = os_; TS[i] = lower if os_ else upper
    d = pd.DataFrame(index=df.index)
    d["o"], d["h"], d["l"], d["c"], d["atr"], d["os"], d["ts"], d["perf_idx"], d["tf"] = o, h, l, c, atr, OS, TS, PI, TF
    # fakeout filter
    ov = np.full(N, np.nan)
    for i in range(10, N):
        s1 = 0; s2 = 0
        for j in range(10):
            s1 += max(0.0, min(h[i-j], h[i-j-1]) - max(l[i-j], l[i-j-1])); s2 += h[i-j] - l[i-j]
        ov[i] = s1 / s2 if s2 > 0 else 0.0
    rank = np.full(N, np.nan)
    for i in range(210, N):
        prev = ov[i-200:i]; rank[i] = np.sum(prev <= ov[i]) / 200 * 100
    body = np.where(atr > 0, np.abs(c - o) / atr, 0)
    maxR = 85 if fakeout == "Light" else 80
    minQ = 0.3; bodyO = 0.6 if fakeout == "Light" else (0.7 if fakeout == "Medium" else 1e10)
    chopOk = np.isnan(rank) | (rank <= maxR)
    qualOk = (np.nan_to_num(PI) >= minQ) | (body >= bodyO)
    passes = (~np.array([filterOn] * N)) | (chopOk & qualOk)
    osp = np.r_[0, OS[:-1]]
    d["rank"], d["body"], d["passes"] = rank, body, passes
    d["flipUp"] = OS > osp; d["flipDn"] = OS < osp
    d["buy"] = d.flipUp & passes; d["sell"] = d.flipDn & passes
    # reversal machinery for the take profit warning
    mean = supersmoother(hlc3, 100); rng = supersmoother(np.nan_to_num(tr, nan=0) if False else tr, 100)
    up2 = mean + rng * math.pi * 2.415; lo2 = mean - rng * math.pi * 2.415
    cond = np.zeros(N, int)
    for i in range(N):
        if c[i] > mean[i]:
            u9 = up2[i] - 2 * rng[i]; u1 = up2[i] + 2 * rng[i]
            cond[i] = 1 if (h[i] >= u9 and h[i] < up2[i]) else 2 if (h[i] >= up2[i] and h[i] < u1) else 3 if h[i] >= u1 else 4 if c[i] <= mean[i] + rng[i] else 5
        elif c[i] < mean[i]:
            l9 = lo2[i] + 2 * rng[i]; l1 = lo2[i] - 2 * rng[i]
            cond[i] = -1 if (l[i] <= l9 and l[i] > lo2[i]) else -2 if (l[i] <= lo2[i] and l[i] > l1) else -3 if l[i] <= l1 else -4 if c[i] >= mean[i] - rng[i] else -5
    fast = 0.75 * oscillator(c, 9); norm = oscillator(c, 20); slow = 1.75 * oscillator(c, 50)
    fp, np_ = np.r_[np.nan, fast[:-1]], np.r_[np.nan, norm[:-1]]
    bearX = (fast < norm) & (fp >= np_) & (norm > 0); bullX = (fast > norm) & (fp <= np_) & (norm < 0)
    def trig(X, bear):
        res = np.zeros(N, bool); vals = []; lastX = -10**9
        yh = gaussian(norm, 6, 6)
        for i in range(N):
            prevX = lastX
            if X[i]:
                smaller = (len(vals) >= 1) and ((norm[i] < vals[-1] * 0.4) if bear else (norm[i] > vals[-1] * 0.4))
                # valuewhen(..., 1) = previous cross value
                divz = (i - 1 - prevX) < 30 if prevX > -10**9 else False
                kt = (yh[i] < slow[i]) if bear else (yh[i] > slow[i])
                res[i] = smaller and divz and kt
                vals.append(norm[i]); lastX = i
        return res
    # barssince(X[1]) < 30 : bars since previous cross measured from the prior bar
    d["bearTW"] = trig(bearX, True); d["bullTW"] = trig(bullX, False)
    d["oscBear"] = (norm < 0) & (np_ >= 0); d["oscBull"] = (norm > 0) & (np_ <= 0)
    d["cond"] = cond
    d["bearEx"] = ((cond >= 2) & (cond <= 3)) | d.bearTW | d.oscBear
    d["bullEx"] = ((cond <= -2) & (cond >= -3)) | d.bullTW | d.oscBull
    return d
