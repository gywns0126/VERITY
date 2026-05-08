-- estate_alerts dedupe_key — estate_brain 자동 alert 중복 방지
-- estate_brain_builder cron 이 매일 실행되며 같은 신호가 매번 insert 되면 노이즈.
-- dedupe_key 산식: f"{YYYY-MM-DD}_{category_subtype}_{complex_id}_{signal_subtype}"
-- → 같은 날 같은 단지 같은 신호는 1 row 만 (ON CONFLICT DO NOTHING).
--
-- 기존 alert (수동/RSS/RSS-collector) 는 dedupe_key NULL → 영향 없음.

ALTER TABLE estate_alerts
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

-- partial unique index (NULL 끼리는 비교 안 됨 → 기존 alert 영향 없음)
CREATE UNIQUE INDEX IF NOT EXISTS idx_estate_alerts_dedupe_uniq
    ON estate_alerts(dedupe_key)
    WHERE dedupe_key IS NOT NULL;
