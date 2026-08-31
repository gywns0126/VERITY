-- CONTRACT phase: run only after the Vercel order function using migration 035
-- has been deployed and its five-argument reservation call has been verified.
-- Keep the old signature as a fail-closed stub instead of deleting the function.

CREATE OR REPLACE FUNCTION public.reserve_order_slot(
    p_order_hash TEXT,
    p_daily_limit INTEGER
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RAISE EXCEPTION 'legacy order reservation RPC disabled; use policy ledger signature'
        USING ERRCODE = '55000';
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_order_slot(TEXT, INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.reserve_order_slot(TEXT, INTEGER) TO authenticated;

COMMENT ON FUNCTION public.reserve_order_slot(TEXT, INTEGER) IS
    'Fail-closed compatibility stub. Live orders must use the five-argument policy-ledger RPC.';
