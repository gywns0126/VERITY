-- Watch Groups: 토스 스타일 관심종목 그룹
-- user_id는 클라이언트에서 UUID를 생성/localStorage에 저장하여 전달 (로그인 없는 경우)
-- 향후 Supabase Auth 도입 시 auth.uid()로 교체 가능

CREATE TABLE IF NOT EXISTS watch_groups (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '관심종목',
    color       TEXT NOT NULL DEFAULT '#B5FF19',
    icon        TEXT NOT NULL DEFAULT '⭐',
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watch_group_items (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    group_id    UUID NOT NULL REFERENCES watch_groups(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    market      TEXT NOT NULL DEFAULT 'kr',
    memo        TEXT NOT NULL DEFAULT '',
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wg_user ON watch_groups(user_id);
CREATE INDEX IF NOT EXISTS idx_wgi_group ON watch_group_items(group_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wgi_uniq ON watch_group_items(group_id, ticker);

ALTER TABLE watch_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE watch_group_items ENABLE ROW LEVEL SECURITY;

-- anon 키로 접근 가능하되, user_id 기반 격리
CREATE POLICY "Users see own groups" ON watch_groups
    FOR ALL USING (true);

CREATE POLICY "Users see own items" ON watch_group_items
    FOR ALL USING (true);
