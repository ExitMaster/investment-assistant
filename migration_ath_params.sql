-- ATH 재계산 트리거용 신규 컬럼 (Supabase SQL Editor에서 1회 실행)
-- ath_state 행이 '어떤 설정값으로 계산됐는지'를 기록한다. 엔진이 매 실행마다 현재 설정과
-- 비교해서 갱신 임계(reset_pct)나 산정 기간(lookback)이 바뀌었으면 히스토리로 재계산한다.
ALTER TABLE ath_state ADD COLUMN IF NOT EXISTS reset_pct_used double precision DEFAULT 10;
ALTER TABLE ath_state ADD COLUMN IF NOT EXISTS lookback_used text DEFAULT '5y';
