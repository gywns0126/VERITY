-- Harden RLS for watch groups/items.
-- This migration expects API to pass x-user-id header.

CREATE OR REPLACE FUNCTION public.requesting_user_id()
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE((current_setting('request.headers', true)::json ->> 'x-user-id'), '');
$$;

DROP POLICY IF EXISTS "Users see own groups" ON watch_groups;
DROP POLICY IF EXISTS "Users see own items" ON watch_group_items;

CREATE POLICY watch_groups_select_own ON watch_groups
  FOR SELECT
  USING (user_id = public.requesting_user_id());

CREATE POLICY watch_groups_insert_own ON watch_groups
  FOR INSERT
  WITH CHECK (user_id = public.requesting_user_id());

CREATE POLICY watch_groups_update_own ON watch_groups
  FOR UPDATE
  USING (user_id = public.requesting_user_id())
  WITH CHECK (user_id = public.requesting_user_id());

CREATE POLICY watch_groups_delete_own ON watch_groups
  FOR DELETE
  USING (user_id = public.requesting_user_id());

CREATE POLICY watch_group_items_select_own ON watch_group_items
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1
      FROM watch_groups wg
      WHERE wg.id = watch_group_items.group_id
        AND wg.user_id = public.requesting_user_id()
    )
  );

CREATE POLICY watch_group_items_insert_own ON watch_group_items
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM watch_groups wg
      WHERE wg.id = watch_group_items.group_id
        AND wg.user_id = public.requesting_user_id()
    )
  );

CREATE POLICY watch_group_items_update_own ON watch_group_items
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1
      FROM watch_groups wg
      WHERE wg.id = watch_group_items.group_id
        AND wg.user_id = public.requesting_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM watch_groups wg
      WHERE wg.id = watch_group_items.group_id
        AND wg.user_id = public.requesting_user_id()
    )
  );

CREATE POLICY watch_group_items_delete_own ON watch_group_items
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1
      FROM watch_groups wg
      WHERE wg.id = watch_group_items.group_id
        AND wg.user_id = public.requesting_user_id()
    )
  );
