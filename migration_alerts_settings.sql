-- D/E 작업용 신규 컬럼 (Supabase SQL Editor에서 1회 실행)
-- 1) 알림 마스터 차단 (알림 탭의 '알림 전체 차단' 토글)
ALTER TABLE settings ADD COLUMN IF NOT EXISTS alerts_master_off boolean NOT NULL DEFAULT false;
-- 2) 매매 행동 가이드 알림 포함 여부 (기본 포함)
ALTER TABLE settings ADD COLUMN IF NOT EXISTS include_action_guide boolean NOT NULL DEFAULT true;
