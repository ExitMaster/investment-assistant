-- 관리자 텔레그램 알림용 컬럼 추가
-- Supabase SQL Editor에서 직접 실행할 것 (커넥터로 자동 반영 안 됨).

-- 신규 가입 요청을 관리자에게 통지했는지 여부.
-- 엔진(telegram_link.py)이 status=pending AND admin_notified=false 인 사용자를 찾아
-- 관리자에게 알린 뒤 true로 표시한다.
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS admin_notified boolean NOT NULL DEFAULT false;

-- 기존 사용자는 관리자가 이미 알고 있으므로 통지 대상에서 제외(첫 실행 시 도배 방지).
UPDATE profiles SET admin_notified = true WHERE admin_notified = false;

-- 텔레그램 연결 해지 알림 대기 플래그.
-- 웹앱(Alerts.jsx)이 해지 시 true로 설정 → 엔진이 관리자에게 통지 후 false로 되돌린다.
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS admin_unlink_notify boolean NOT NULL DEFAULT false;
