"""
알림 메시지 발송 테스트 (관리자 전용).

- DB는 **읽기만** 한다(관리자 chat_id 조회). alerts·ath_state·profiles 등 어떤 테이블에도
  쓰지 않으므로 실제 알림이 발생한 것처럼 기록이 남지 않는다.
- 모든 알림 유형의 샘플 메시지를 관리자에게만 보낸다. 각 메시지 앞에 [테스트] 배지를 붙인다.

실행: GitHub Actions의 "test-notify" 워크플로를 수동(workflow_dispatch)으로 돌리거나,
      로컬에서 TELEGRAM_BOT_TOKEN·SUPABASE_URL·SUPABASE_SECRET_KEY 환경변수 세팅 후
      `python engine/test_notify.py`.
"""
import db
import notify

TAG = "🧪 <b>[테스트]</b> 실제 신호 아님 · DB 미기록\n\n"


def _samples():
    """(설명, 메시지본문) 목록. 모든 알림 유형을 한 번씩 만든다."""
    out = []

    # ── 사용자 알림 유형 ──────────────────────────────────────────
    out.append(("매수 신호 (기본 색상)", notify.format_buy_level(
        "QQQ", 10, 412.35, 458.17, -10.3, name=None,
        action={"product": "QLD", "cash": 40},
        prev_close=417.40, next_level=20, next_gap=9.7)))

    out.append(("매수 신호 (색상 반전)", notify.format_buy_level(
        "QQQ", 10, 412.35, 458.17, -10.3, name=None,
        action={"product": "QLD", "cash": 40}, inverted=True,
        prev_close=417.40, next_level=20, next_gap=9.7)))

    out.append(("매수레벨 임박", notify.format_prealert(
        "QQQ", 20, 380.10, 458.17, -17.0, 3.0, name=None,
        action={"product": "QQQ", "cash": 20})))

    out.append(("매도 신호 (ATH 도달, 기본 색상)", notify.format_sell(
        "QQQ", 0, 458.20, 458.17, 0.0, name=None, cash_target=50,
        prev_close=452.10, next_level=10, next_gap=10.0)))

    out.append(("매도 신호 (+10%, 색상 반전)", notify.format_sell(
        "QQQ", 10, 504.00, 458.17, 10.0, name=None, cash_target=50, inverted=True,
        prev_close=499.30, next_level=20, next_gap=10.0)))

    out.append(("매도레벨 임박", notify.format_prealert_sell(
        "QQQ", 10, 498.00, 458.17, 8.7, 1.3, name=None)))

    # 보조지표: 실제로 발생한 신호만 bullet으로 표기됨(아래는 일부만 True인 현실적 예시)
    out.append(("보조지표 매수", notify.format_indicator("005930.KS", {
        "dmi_buy": True,
        "bull_div": True,
        "dmi_values": {"minus_di": 28.3, "adx": 22.1},
        "bull_div_values": {"k1": 12, "k2": 25},
    }, name="삼성전자")))

    out.append(("보조지표 매도", notify.format_sell_indicator("QQQ", {
        "high_vol_breakout": True,
        "vol_ratio": 3.1,
    }, name=None)))

    out.append(("개별주식 DMI", notify.format_watchlist("AAPL", {
        "dmi_values": {"minus_di": 30.5, "adx": 25.0},
    }, name=None)))

    # ── 관리자 알림 유형 ──────────────────────────────────────────
    out.append(("관리자: 신규 가입 요청", notify.format_admin_new_user(
        "홍길동", "test.user@gmail.com")))

    out.append(("관리자: 텔레그램 연결됨", notify.format_admin_tg_linked(
        "홍길동", "test.user@gmail.com", "@hong_gildong")))

    out.append(("관리자: 텔레그램 연결 해지", notify.format_admin_tg_unlinked(
        "홍길동", "test.user@gmail.com")))

    return out


def main():
    chat_ids = db.get_admin_chat_ids()
    if not chat_ids:
        print("[test] 발송 대상 관리자(role=admin·텔레그램 연결됨)가 없습니다.")
        return

    print(f"[test] 관리자 {len(chat_ids)}명에게 샘플 발송 시작")
    samples = _samples()
    for chat_id in chat_ids:
        for desc, body in samples:
            ok = notify.send_message(chat_id, TAG + body)
            print(f"  - {desc}: {'OK' if ok else 'FAIL'} (chat={chat_id})")
    print("[test] 완료. DB에는 아무것도 기록하지 않았습니다.")


if __name__ == "__main__":
    main()
