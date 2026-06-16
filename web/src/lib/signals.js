// 엔진(engine/indicators.py, signals.py) 로직의 브라우저 포팅.
// 백테스트 시각화 전용 — 과거 일봉에서 매수레벨/매도/보조지표 신호가
// 언제·왜 떴는지 계산한다. run.py backtest 결과와 날짜가 일치하도록 맞춤.

// ── 기본 수치 헬퍼 ──
function diff(a) {
  const out = new Array(a.length).fill(0);
  for (let i = 1; i < a.length; i++) out[i] = a[i] - a[i - 1];
  return out;
}
// Wilder/EMA (pandas ewm adjust=False): y0=x0, yt = a*xt + (1-a)*y(t-1)
function ewm(x, alpha) {
  const out = new Array(x.length).fill(NaN);
  let prev = null;
  for (let i = 0; i < x.length; i++) {
    const v = x[i];
    if (prev === null) { prev = v; out[i] = v; }
    else { prev = alpha * v + (1 - alpha) * prev; out[i] = prev; }
  }
  return out;
}
function rollingMin(x, w) {
  const out = new Array(x.length).fill(NaN);
  for (let i = w - 1; i < x.length; i++) {
    let m = Infinity;
    for (let j = i - w + 1; j <= i; j++) if (x[j] < m) m = x[j];
    out[i] = m;
  }
  return out;
}
function rollingMax(x, w) {
  const out = new Array(x.length).fill(NaN);
  for (let i = w - 1; i < x.length; i++) {
    let m = -Infinity;
    for (let j = i - w + 1; j <= i; j++) if (x[j] > m) m = x[j];
    out[i] = m;
  }
  return out;
}
function rollingMean(x, w) {
  const out = new Array(x.length).fill(NaN);
  for (let i = w - 1; i < x.length; i++) {
    let s = 0, ok = true;
    for (let j = i - w + 1; j <= i; j++) { if (Number.isNaN(x[j])) { ok = false; break; } s += x[j]; }
    out[i] = ok ? s / w : NaN;
  }
  return out;
}

// ── ATH 확정-고점 시계열 (compute_ath_state의 증분판) ──
// 각 봉 시점의 ATH 기준선 배열을 반환. ATH는 고점에서 resetPct% 눌림이
// 확정될 때만, 위로만 갱신된다.
export function athSeries(close, resetPct = 10) {
  const r = resetPct / 100;
  const out = new Array(close.length).fill(NaN);
  let ath = close[0];
  let peak = close[0];
  for (let i = 0; i < close.length; i++) {
    const c = close[i];
    if (c > peak) peak = c;
    if (c <= peak * (1 - r)) {
      if (peak > ath) ath = peak;
      peak = c;
    }
    out[i] = ath;
  }
  return out;
}

// ── DMI (Wilder) ──
function wilderDMI(high, low, close, period = 14) {
  const up = diff(high), down = diff(low).map((d) => -d);
  const plusDM = up.map((u, i) => (u > down[i] && u > 0 ? u : 0));
  const minusDM = down.map((dn, i) => (dn > up[i] && dn > 0 ? dn : 0));
  const tr = high.map((h, i) => {
    if (i === 0) return h - low[i];
    return Math.max(h - low[i], Math.abs(h - close[i - 1]), Math.abs(low[i] - close[i - 1]));
  });
  const a = 1 / period;
  const atr = ewm(tr, a);
  const plusDI = ewm(plusDM, a).map((v, i) => (atr[i] ? (100 * v) / atr[i] : 0));
  const minusDI = ewm(minusDM, a).map((v, i) => (atr[i] ? (100 * v) / atr[i] : 0));
  const dx = plusDI.map((p, i) => {
    const den = p + minusDI[i];
    return den ? (100 * Math.abs(p - minusDI[i])) / den : 0;
  });
  const adx = ewm(dx, a);
  return { plusDI, minusDI, adx };
}

// ── Stochastics Slow (5,3,3) ──
function stochSlow(high, low, close, k = 5, d = 3, smooth = 3) {
  const ll = rollingMin(low, k), hh = rollingMax(high, k);
  const fastK = close.map((c, i) => {
    const den = hh[i] - ll[i];
    return den ? (100 * (c - ll[i])) / den : NaN;
  });
  const slowK = rollingMean(fastK, smooth);
  const slowD = rollingMean(slowK, d);
  return { slowK, slowD };
}

// ── 스윙 피벗 (좌우 width 봉보다 낮은/높은 확정 피벗) ──
function findPivots(s, width = 3) {
  const lows = [], highs = [];
  for (let i = width; i < s.length - width; i++) {
    let isMin = true, isMax = true;
    for (let j = i - width; j <= i + width; j++) {
      if (s[j] < s[i]) isMin = false;
      if (s[j] > s[i]) isMax = false;
    }
    if (isMin && s[i] < s[i - 1] && s[i] < s[i + 1]) lows.push(i);
    if (isMax && s[i] > s[i - 1] && s[i] > s[i + 1]) highs.push(i);
  }
  return { lows, highs };
}

// 마지막 봉 부근에서 새 피벗이 확정될 때만 신호 (run.py backtest와 동일)
function bullishDivergence(lowSub, skSub, width = 3) {
  const { lows } = findPivots(lowSub, width);
  if (lows.length < 2) return null;
  const i1 = lows[lows.length - 2], i2 = lows[lows.length - 1];
  const n = lowSub.length;
  if (n - 1 - (i2 + width) > 1) return null;
  if (lowSub[i2] < lowSub[i1] && skSub[i2] > skSub[i1] && skSub[n - 1] > skSub[i2])
    return { k1: round1(skSub[i1]), k2: round1(skSub[i2]) };
  return null;
}
function bearishDivergence(highSub, skSub, width = 3) {
  const { highs } = findPivots(highSub, width);
  if (highs.length < 2) return null;
  const i1 = highs[highs.length - 2], i2 = highs[highs.length - 1];
  const n = highSub.length;
  if (n - 1 - (i2 + width) > 1) return null;
  if (highSub[i2] > highSub[i1] && skSub[i2] < skSub[i1] && skSub[n - 1] < skSub[i2])
    return { k1: round1(skSub[i1]), k2: round1(skSub[i2]) };
  return null;
}

// ── 저점/고점 대량거래 돌파 (sub 윈도우 기준, 마지막 봉 확정) ──
function volumeBreakout(high, low, close, vol, end, lookback = 126, confirm = 3, trendMA = 60) {
  const n = end + 1;
  if (n < trendMA) return null;
  const start = Math.max(0, n - lookback);
  let maxI = start, maxV = -Infinity;
  for (let i = start; i < n; i++) if (vol[i] > maxV) { maxV = vol[i]; maxI = i; }
  const barsSince = n - 1 - maxI;
  if (barsSince < 0 || barsSince > confirm) return null;
  // maxI 시점의 60MA
  if (maxI < trendMA - 1) return null;
  let s = 0;
  for (let j = maxI - trendMA + 1; j <= maxI; j++) s += close[j];
  const barMA = s / trendMA;
  const barClose = close[maxI];
  const price = close[n - 1];
  // 거래량 배수 (최근 lookback 중앙값 대비)
  const slice = vol.slice(start, n).slice().sort((a, b) => a - b);
  const med = slice.length ? slice[Math.floor(slice.length / 2)] : 1;
  const ratio = round1(vol[maxI] / Math.max(med, 1e-9));
  if (barClose < barMA && price > high[maxI]) return { kind: "low", ratio };
  if (barClose > barMA && price < low[maxI]) return { kind: "high", ratio };
  return null;
}

function round1(x) { return Math.round(x * 10) / 10; }

// ── 백테스트 메인 ──
// data: {time, open, high, low, close, volume}
// settings: {resetPct, levels, sellLevels, dmiThreshold, stochParams, volumeLookback}
export function runBacktest(data, settings = {}) {
  const { time, high, low, close, volume } = data;
  const n = close.length;
  const resetPct = settings.resetPct ?? 10;
  const levels = (settings.levels ?? [10, 20, 30, 40]).slice().sort((a, b) => a - b);
  const sellLevels = (settings.sellLevels ?? [0, 10, 20, 30]).slice().sort((a, b) => a - b);
  const thr = settings.dmiThreshold ?? 30;
  const sp = settings.stochParams ?? [5, 3, 3];
  const lookback = settings.volumeLookback ?? 126;

  const ath = athSeries(close, resetPct);
  const { minusDI, adx } = wilderDMI(high, low, close);
  const { slowK } = stochSlow(high, low, close, sp[0], sp[1], sp[2]);

  const events = [];
  // ATH가 바뀌어야만 같은 레벨 재발화 허용 (엔진의 level_last_alert와 동일 로직)
  const buyFiredAtAth = {};   // level → 마지막으로 발화한 ATH 값
  const sellFiredAtAth = {};  // level → 마지막으로 발화한 ATH 값

  // 보조지표 신호 중복 억제 (false→true 전환 시에만)
  let prevDmiBuy = false, prevDmiImm = false, prevBull = false, prevBear = false, prevLowVol = false, prevHighVol = false;

  const warmup = 70; // run.py backtest와 동일 시작점

  for (let i = 1; i < n; i++) {
    const a = ath[i];
    const dd = ((a - close[i]) / a) * 100; // 하락률(양수=하락)
    const gain = ((close[i] - a) / a) * 100; // ATH 초과 상승률

    // 매수 레벨: 동일 ATH에서 레벨당 1회만 (ATH가 바뀌면 재발화)
    for (const L of levels) {
      if (dd >= L && buyFiredAtAth[L] !== a) {
        buyFiredAtAth[L] = a;
        events.push({
          time: time[i], type: "buy_level", price: close[i],
          label: `매수 -${L}%`,
          reason: `ATH 대비 -${L}% 도달 (현재 ${dd.toFixed(1)}%, ATH ${fmt(a)})`,
        });
      }
    }

    // 매도 레벨: 동일 ATH에서 레벨당 1회만 (ATH가 바뀌면 재발화)
    for (const L of sellLevels) {
      if (gain >= L && sellFiredAtAth[L] !== a) {
        sellFiredAtAth[L] = a;
        events.push({
          time: time[i], type: "sell", price: close[i],
          label: L === 0 ? "매도 ATH" : `매도 +${L}%`,
          reason: L === 0
            ? `ATH 도달 (ATH ${fmt(a)})`
            : `ATH 대비 +${L}% 초과 (현재 +${gain.toFixed(1)}%)`,
        });
      }
    }

    if (i < warmup) continue;

    // DMI 매수신호: 30 이상에서 DI- 가 ADX 하향돌파
    const dmiBuy =
      minusDI[i - 1] >= adx[i - 1] && minusDI[i] < adx[i] &&
      minusDI[i - 1] >= thr && adx[i - 1] >= thr;
    if (dmiBuy && !prevDmiBuy) {
      events.push({
        time: time[i], type: "dmi_buy", price: close[i], label: "DMI 매수",
        reason: `DI- 하향돌파 (DI-=${round1(minusDI[i])}, ADX=${round1(adx[i])})`,
      });
    }
    prevDmiBuy = dmiBuy;

    // DMI 임박: 둘 다 30 이상, DI- 가 ADX 바로 위 근접
    const m = minusDI[i], ax = adx[i];
    const dmiImm = m >= thr && ax >= thr && m - ax >= 0 && m - ax <= 3.0;
    if (dmiImm && !prevDmiImm && !dmiBuy) {
      events.push({
        time: time[i], type: "dmi_imminent", price: close[i], label: "DMI 임박",
        reason: `DI- ≳ ADX 근접 (DI-=${round1(m)}, ADX=${round1(ax)})`,
      });
    }
    prevDmiImm = dmiImm;

    // 다이버전스 (sub 윈도우)
    const bull = bullishDivergence(low.slice(0, i + 1), slowK.slice(0, i + 1));
    if (bull && !prevBull) {
      events.push({
        time: time[i], type: "bull_div", price: close[i], label: "상승 다이버전스",
        reason: `주가 저점↓ · %K 저점↑ (%K ${bull.k1}→${bull.k2} 상향)`,
      });
    }
    prevBull = !!bull;

    const bear = bearishDivergence(high.slice(0, i + 1), slowK.slice(0, i + 1));
    if (bear && !prevBear) {
      events.push({
        time: time[i], type: "bear_div", price: close[i], label: "하락 다이버전스",
        reason: `주가 고점↑ · %K 고점↓ (%K ${bear.k1}→${bear.k2} 하향)`,
      });
    }
    prevBear = !!bear;

    // 대량거래 돌파
    const vb = volumeBreakout(high, low, close, volume, i, lookback);
    const lowVol = vb && vb.kind === "low";
    const highVol = vb && vb.kind === "high";
    if (lowVol && !prevLowVol) {
      events.push({
        time: time[i], type: "low_vol", price: close[i], label: "저점 대량거래",
        reason: `하락추세 최대거래량 봉 고가 돌파 (거래량 x${vb.ratio})`,
      });
    }
    if (highVol && !prevHighVol) {
      events.push({
        time: time[i], type: "high_vol", price: close[i], label: "고점 대량거래",
        reason: `상승추세 최대거래량 봉 저가 이탈 (거래량 x${vb.ratio})`,
      });
    }
    prevLowVol = lowVol;
    prevHighVol = highVol;
  }

  return { athSeries: ath, events, currentAth: ath[n - 1] };
}

function fmt(x) {
  return x >= 1000 ? Math.round(x).toLocaleString() : x.toFixed(2);
}

// 신호 종류별 마커 색/표기 (lightweight-charts)
export const SIGNAL_STYLE = {
  buy_level:    { color: "#22c55e", position: "belowBar", shape: "arrowUp",   text: "매수" },
  sell:         { color: "#ef4444", position: "aboveBar", shape: "arrowDown", text: "매도" },
  dmi_buy:      { color: "#3b82f6", position: "belowBar", shape: "circle",    text: "DMI" },
  dmi_imminent: { color: "#60a5fa", position: "belowBar", shape: "circle",    text: "DMI?" },
  bull_div:     { color: "#14b8a6", position: "belowBar", shape: "circle",    text: "Div+" },
  bear_div:     { color: "#f97316", position: "aboveBar", shape: "circle",    text: "Div-" },
  low_vol:      { color: "#a855f7", position: "belowBar", shape: "square",    text: "Vol+" },
  high_vol:     { color: "#eab308", position: "aboveBar", shape: "square",    text: "Vol-" },
};
