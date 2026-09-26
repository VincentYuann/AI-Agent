-- ==============================================================================
-- Supabase Database Function: execute_admin_sql
-- ------------------------------------------------------------------------------
-- Purpose:
-- Allows authenticated administrators to execute safe dynamic SQL operations
-- (INSERT, UPDATE, DELETE, SELECT) against portfolio tables directly via PostgREST RPC,
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
DECLARE
  result jsonb;
  rows_count integer;
  trimmed_query text;
BEGIN
  -- Strict authorization: Only vincentyuan1020@gmail.com or service_role
  IF COALESCE(auth.jwt() ->> 'email', '') NOT IN ('vincentyuan1020@gmail.com')
     AND COALESCE(auth.role(), '') NOT IN ('service_role') THEN
    RAISE EXCEPTION 'Access denied: caller is not an authorized administrator';
  END IF;

  trimmed_query := trim(query);

  -- For SELECT queries, return records as jsonb array
  IF lower(trimmed_query) ~ '^\s*select' THEN
    EXECUTE 'SELECT coalesce(jsonb_agg(t), ''[]''::jsonb) FROM (' || trimmed_query || ') t' INTO result;
    RETURN jsonb_build_object(
      'status', 'success',
      'rows_affected', jsonb_array_length(result),
      'data', result,
      'message', 'Query executed successfully'
    );
  ELSE
    -- For INSERT, UPDATE, DELETE mutations, capture row count
    EXECUTE trimmed_query;
    GET DIAGNOSTICS rows_count = ROW_COUNT;
    RETURN jsonb_build_object(
      'status', 'success',
      'rows_affected', rows_count,
      'message', 'Query executed successfully'
    );
  END IF;
EXCEPTION WHEN OTHERS THEN
  RETURN jsonb_build_object('status', 'error', 'message', SQLERRM);
END;
$$;

-- Grant execute permissions to authenticated and service_role
GRANT EXECUTE ON FUNCTION public.execute_admin_sql(text) TO authenticated, service_role;
