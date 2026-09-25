-- ==============================================================================
-- Supabase Database Function: get_portfolio_ai_context
-- ------------------------------------------------------------------------------
-- Purpose:
-- Aggregates all portfolio knowledge (profile, projects, experience, philosophy)
-- into a single, structured JSON document tailored specifically for AI consumption.
--
-- AI Filtering Rules (Zero-Leakage & Byte-Efficiency):
-- 1. Strips internal database IDs, created_at, and updated_at timestamps.
-- 2. Strips heavy binary/URL assets (e.g. project image URLs, experience logo URLs).
-- 3. Strips 'images' array and 'displayOrder' from profile hobbies.
-- 4. Normalizes overview/description fallbacks.
-- 5. Orders projects and experience by display_order ASC, and philosophy by position ASC.
--
-- Security:
-- SECURITY DEFINER with search_path = public ensures safe execution across roles.
-- ==============================================================================

CREATE OR REPLACE FUNCTION public.get_portfolio_ai_context()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result jsonb;
BEGIN
  SELECT jsonb_build_object(
    'candidate', 'Vincent Yuan',
    'profile', (
      SELECT jsonb_build_object(
        'name', p.name,
        'role', p.role,
        'headline', p.headline,
        'tagline', p.tagline,
        'email', p.email,
        'github', p.github,
        'linkedin', p.linkedin,
        'capability_pillars', to_jsonb(p.capability_pillars),
        'hanko_card', to_jsonb(p.hanko_card),
        'origin_story', to_jsonb(p.origin_story),
        'hobbies', (
          SELECT COALESCE(
            jsonb_agg(
              -- Strip heavy image URLs, displayOrder, and database IDs from hobbies
              h - 'images' - 'displayOrder' - 'id'
            ),
            '[]'::jsonb
          )
          FROM jsonb_array_elements(
            CASE 
              WHEN jsonb_typeof(to_jsonb(p.hobbies)) = 'array' THEN to_jsonb(p.hobbies)
              ELSE '[]'::jsonb 
            END
          ) AS h
        )
      )
      FROM profile p
      WHERE p.id = 1
      LIMIT 1
    ),
    'projects', (
      SELECT COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'title', pr.title,
            'subtitle', pr.subtitle,
            'category', pr.category,
            'badge', pr.badge,
            'kanji', pr.kanji,
            'status_label', pr.status_label,
            'is_active', pr.is_active,
            'is_featured', pr.is_featured,
            'tech_stacks', to_jsonb(pr.tech_stacks),
            'overview', COALESCE(NULLIF(pr.overview, ''), pr.description),
            'bullets', to_jsonb(pr.bullets),
            'start_date', pr.start_date,
            'end_date', pr.end_date,
            'github_link', pr.github_link,
            'live_link', pr.live_link
          )
          ORDER BY pr.display_order ASC NULLS LAST, pr.created_at ASC
        ),
        '[]'::jsonb
      )
      FROM projects pr
    ),
    'experience', (
      SELECT COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'title', e.title,
            'company', e.company,
            'location', e.location,
            'start_date', e.start_date,
            'end_date', e.end_date,
            'is_active', e.is_active,
            'status_label', e.status_label,
            'kanji', e.kanji,
            'kanji_subtitle', e.kanji_subtitle,
            'tags', to_jsonb(e.tags),
            'overview', COALESCE(NULLIF(e.overview, ''), e.description),
            'bullets', to_jsonb(e.bullets)
          )
          ORDER BY e.display_order ASC NULLS LAST, e.created_at ASC
        ),
        '[]'::jsonb
      )
      FROM experience e
    ),
    'philosophy', (
      SELECT COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'kanji', ph.kanji,
            'romaji', ph.romaji,
            'title', ph.title,
            'tag', ph.tag,
            'description', ph.description
          )
          ORDER BY ph.position ASC NULLS LAST
        ),
        '[]'::jsonb
      )
      FROM philosophy_pillars ph
    )
  ) INTO result;

  RETURN result;
END;
$$;

-- Grant execution permissions to anon, authenticated, and service_role
GRANT EXECUTE ON FUNCTION public.get_portfolio_ai_context() TO anon, authenticated, service_role;
