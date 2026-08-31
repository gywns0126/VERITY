-- Persist the server-side policy decision with every live-order reservation.
-- This replaces the two-argument RPC from migration 032.

ALTER TABLE public.order_reservations
    ADD COLUMN IF NOT EXISTS policy_mode TEXT,
    ADD COLUMN IF NOT EXISTS policy_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS override_reason TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'order_reservations_policy_mode_check'
          AND conrelid = 'public.order_reservations'::regclass
    ) THEN
        ALTER TABLE public.order_reservations
            ADD CONSTRAINT order_reservations_policy_mode_check
            CHECK (policy_mode IS NULL OR policy_mode IN ('manual', 'advised', 'enforced'));
    END IF;
END;
$$;

-- The legacy two-argument overload remains available during this expansion phase.
-- Retire it only after the Vercel function using the five-argument RPC is live and verified.

CREATE OR REPLACE FUNCTION public.reserve_order_slot(
    p_order_hash TEXT,
    p_daily_limit INTEGER,
    p_policy_mode TEXT,
    p_policy_snapshot JSONB,
    p_override_reason TEXT
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
    IF p_policy_mode NOT IN ('manual', 'advised', 'enforced') THEN
        RAISE EXCEPTION 'invalid policy mode' USING ERRCODE = '22023';
    END IF;
    IF jsonb_typeof(COALESCE(p_policy_snapshot, '{}'::jsonb)) <> 'object' THEN
        RAISE EXCEPTION 'invalid policy snapshot' USING ERRCODE = '22023';
    END IF;
    IF p_policy_mode = 'manual' AND NULLIF(btrim(COALESCE(p_override_reason, '')), '') IS NULL THEN
        RAISE EXCEPTION 'manual override reason required' USING ERRCODE = '22023';
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

    INSERT INTO public.order_reservations (
        user_id,
        order_hash,
        order_day,
        policy_mode,
        policy_snapshot,
        override_reason
    )
    VALUES (
        v_uid,
        p_order_hash,
        v_today,
        p_policy_mode,
        COALESCE(p_policy_snapshot, '{}'::jsonb),
        NULLIF(btrim(COALESCE(p_override_reason, '')), '')
    )
    RETURNING id INTO v_id;

    RETURN jsonb_build_object('ok', true, 'reservation_id', v_id, 'count', v_count + 1);
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_order_slot(TEXT, INTEGER, TEXT, JSONB, TEXT)
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.reserve_order_slot(TEXT, INTEGER, TEXT, JSONB, TEXT)
    TO authenticated;

COMMENT ON COLUMN public.order_reservations.policy_snapshot IS
    'Server-side live balance, quote, exposure and moderation decision captured before execution.';
