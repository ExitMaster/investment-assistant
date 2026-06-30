// 국내 지수/종목 시세를 네이버 금융에서 직접 가져온다.
// Yahoo는 국내 지수(^KQ11 등) 전일종가가 깨져 있고 등락률 필드도 없어, 국내는 네이버를
// 단일 소스로 사용한다. 네이버는 공식 등락률(fluctuationsRatio)을 직접 제공.
// 서버사이드(Vercel 함수)에서만 호출 — 브라우저 직접 호출은 CORS로 막힘.

// 지수 심볼 매핑: 신규 KOSPI/KOSDAQ + 레거시 ^KS11/^KQ11 모두 수용
const INDEX_CODE = { KOSPI: "KOSPI", KOSDAQ: "KOSDAQ", "^KS11": "KOSPI", "^KQ11": "KOSDAQ" };

// 이 심볼이 네이버 대상인지 판별. 대상이면 {kind, code} 반환(아니면 null).
export function naverKind(sym) {
  if (sym in INDEX_CODE) return { kind: "index", code: INDEX_CODE[sym] };
  if (/^\d{6}$/.test(sym)) return { kind: "stock", code: sym };
  return null;
}

const _num = (s) => (s == null || s === "" ? null : Number(String(s).replace(/,/g, "")));

const _headers = {
  "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
  Accept: "application/json",
  Referer: "https://m.stock.naver.com/",
};

// 단일 국내 심볼 시세 → { price, prevClose, changePct, name } (실패 시 null)
export async function naverQuote(sym) {
  const k = naverKind(sym);
  if (!k) return null;
  try {
    const r = await fetch(`https://m.stock.naver.com/api/${k.kind}/${k.code}/basic`, { headers: _headers });
    if (!r.ok) return null;
    const d = await r.json();
    const price = _num(d.closePrice);
    if (price == null) return null;
    const changePct = _num(d.fluctuationsRatio); // 이미 부호 포함된 공식 등락률
    // 전일종가 = 현재가 - 등락폭(방향 반영). compareToPreviousClosePrice는 부호가 없을 수 있어
    // compareToPreviousPrice.name(RISING/FALLING)으로 부호를 결정한다.
    const mag = Math.abs(_num(d.compareToPreviousClosePrice) ?? 0);
    const dir = d.compareToPreviousPrice?.name;
    const signed = dir === "FALLING" ? -mag : mag;
    const prevClose = price - signed;
    const name = d.stockName || k.code;
    return { price, prevClose, changePct, name };
  } catch {
    return null;
  }
}
