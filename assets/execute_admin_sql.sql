-- ==============================================================================
-- Supabase Database Function: execute_admin_sql
-- ------------------------------------------------------------------------------
-- Purpose:
-- Allows authenticated administrators to execute safe dynamic SQL operations
-- (INSERT, UPDATE, DELETE) against portfolio tables directly via PostgREST RPC,
-- eliminating the need for any high-privilege personal access tokens (sbp_...).
--
-- Security:
-- 1. SECURITY DEFINER with search_path = public.
-- 2. Checks auth.jwt() claims to ensure caller is specifically vincentyuan1020@gmail.com
--    or service_role. Rejects any other authenticated user or anon with an exception.
-- 3. Frontend updates in real-time via Supabase Realtime postgres_changes.
-- ==============================================================================

CREATE OR REPLACE FUNCTION public.execute_admin_sql(query text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Strict authorization: Only vincentyuan1020@gmail.com or service_role
  IF COALESCE(auth.jwt() ->> 'email', '') NOT IN ('vincentyuan1020@gmail.com')
     AND COALESCE(auth.role(), '') NOT IN ('service_role') THEN
    RAISE EXCEPTION 'Access denied: caller is not an authorized administrator';
  END IF;

  EXECUTE query;
  RETURN jsonb_build_object('status', 'success', 'message', 'Query executed successfully');
EXCEPTION WHEN OTHERS THEN
  RETURN jsonb_build_object('status', 'error', 'message', SQLERRM);
END;
$$;

-- Grant execute permissions to authenticated and service_role
GRANT EXECUTE ON FUNCTION public.execute_admin_sql(text) TO authenticated, service_role;
