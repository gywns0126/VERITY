-- 실주문 중복·일일 횟수 원장.
-- Vercel 함수 인스턴스가 달라도 사용자별 advisory lock 안에서 원자적으로 예약한다.

CREATE TABLE IF NOT EXISTS public.order_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    order_hash TEXT NOT NULL CHECK (char_length(order_hash) = 64),
    order_day DATE NOT NULL DEFAULT ((now() AT TIME ZONE 'UTC')::date),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_reservations_user_day
    ON public.order_reservations (user_id, order_day, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_reservations_recent_hash
    ON public.order_reservations (user_id, order_hash, created_at DESC);

ALTER TABLE public.order_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.order_reservations FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.reserve_order_slot(
    p_order_hash TEXT,
    p_daily_limit INTEGER
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_uid UUID := auth.uid();
    v_today DATE := (now() AT TIME ZONE 'UTC')::date;
    v_count INTEGER;
    v_id UUID;
BEGIN
    IF v_uid IS NULL THEN
        RAISE EXCEPTION 'authentication required' USING ERRCODE = '42501';
    END IF;
    IF p_order_hash !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'invalid order hash' USING ERRCODE = '22023';
    END IF;
    IF p_daily_limit < 1 OR p_daily_limit > 1000 THEN
        RAISE EXCEPTION 'invalid daily limit' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(v_uid::text, 0));

    IF EXISTS (
        SELECT 1
        FROM public.order_reservations
        WHERE user_id = v_uid
          AND order_hash = p_order_hash
          AND created_at >= now() - interval '30 seconds'
    ) THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'duplicate');
    END IF;

    SELECT count(*) INTO v_count
    FROM public.order_reservations
    WHERE user_id = v_uid AND order_day = v_today;

    IF v_count >= p_daily_limit THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'daily_limit', 'count', v_count);
    END IF;

    INSERT INTO public.order_reservations (user_id, order_hash, order_day)
    VALUES (v_uid, p_order_hash, v_today)
    RETURNING id INTO v_id;

    RETURN jsonb_build_object('ok', true, 'reservation_id', v_id, 'count', v_count + 1);
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_order_slot(TEXT, INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.reserve_order_slot(TEXT, INTEGER) TO authenticated;

COMMENT ON TABLE public.order_reservations IS
    '실주문 전 원자적 예약 원장. 서버리스 인스턴스 간 30초 중복·UTC 일일 횟수 제한을 공유한다.';
