ADMIN-ONLY TOOL: Executes a validated, safe PostgreSQL SQL statement directly against Vincent's Supabase database to add, update, or edit portfolio tables.

================================================================================
1. DOMAIN CLASSIFICATION & SEMANTIC ENTITY RULES
================================================================================
- public.projects: Designated strictly for software products, tools, web/mobile applications, libraries, open-source repositories, or games that Vincent engineered or contributed to.
- public.experience: Designated strictly for employment, internships, co-ops, client work, part-time jobs, retail/service roles, and commercial workplaces. Any company or commercial employer MUST be placed in `experience`.
- Anti-Hallucination Mandate: NEVER invent fictional engineering architectures (e.g. automated ETL pipelines, distributed clusters) for real-world non-technical service or retail roles. Ground duties authentically in customer service, POS operations, inventory management, or as described in Vincent's resume/profile.
- Strict Non-Destructive / Additive Upsert Rule: Resumes and CVs are role-targeted and omit older entries. Omission of an existing project or job from a resume NEVER implies deletion. Never delete unmentioned records unless explicitly commanded with "delete" or "remove".

================================================================================
2. TABLE SCHEMAS, FIELD SEMANTICS & POSTGRESQL DATA TYPES
================================================================================

TABLE 1: public.profile (Single singleton row, id = 1)
- id: integer (PRIMARY KEY, always 1)
- name: text — Vincent's full professional name ('Vincent Yuan').
- role: text — Primary professional identity shown in hero badge (e.g. 'Full-Stack Software Engineer · Systems Architecture & AI').
- headline: text — Main H1 hero punchline statement on homepage (e.g. 'Architecting resilient, local-first intelligence and high-throughput systems.').
- tagline: text — Secondary narrative biography paragraph expanding on his engineering approach and philosophy.
- email: text — Contact email address ('vincentyuan1020@gmail.com').
- github: text — GitHub profile URL ('https://github.com/VincentYuann').
- linkedin: text — LinkedIn profile URL.
- capability_pillars: jsonb — Array of up to 3 domain cards shown in intro:
    [{"label": "FULL-STACK", "items": "React · TypeScript · Tailwind · Vite", "tags": ["React", "TypeScript", "Tailwind", "Vite"]}]
- hanko_card: jsonb — Traditional Japanese artisan seal card configuration:
    {"headerLabel": "SEAL / 認印", "locationArchive": "PHILADELPHIA, PA", "stampCharacter": "原", "statusBadge": "AVAILABLE FOR WORK", "lines": [{"text": "簡潔な構造美", "label": "CLEAN ARCH", "tooltip": "Clean and intentional system structure"}]}
- origin_story: jsonb — 4-phase personal engineering trajectory rendered in Trajectory section:
    {"badge": "TRAJECTORY & ORIGIN", "headline": "From Hardware Curiosity to Autonomous Systems", "leadParagraph": "...", "milestones": [{"era": "PHASE 01 // 2018–2021", "title": "Foundational Hardware & Systems Curiosity", "subtitle": "Linux kernel & low-level scripting", "tag": "GENESIS", "description": "..."}]}
- hobbies: jsonb — Personal hobbies & passions:
    [{"id": "gaming", "title": "Gaming / League of Legends", "kanji": "遊", "category": "COMPETITIVE ESPORTS", "subtitle": "Grandmaster mid laner", "whyDescription": "...", "images": [], "metadata": [{"label": "PEAK RANK", "value": "Grandmaster"}], "displayOrder": 1}]
- updated_at: timestamptz (Set to NOW())

TABLE 2: public.projects
- id: text (PRIMARY KEY) — Lowercase kebab-case slug identifier (e.g. 'ascension', 'sumi-os', 'ai-agent-copilot').
- title: text — Project title (e.g. 'Ascension').
- subtitle: text — 1-line architectural punchline summarizing technical nature (e.g. '2D Foddian-style physics platformer built with OOP Python').
- category: text — Domain category badge (e.g. 'GAME ARCHITECTURE', 'AI INFRASTRUCTURE', 'FULL STACK WEB', 'SYSTEMS TOOL').
- badge: text — Mirror category or short descriptor pill (e.g. 'ENGINEERING ARCHIVE').
- overview: text — Main technical narrative: problem statement, system architecture, engineering challenges, and solution.
- description: text — Mirror of overview for fallback compatibility.
- bullets: text[] — CRITICAL: Native PostgreSQL text array (ARRAY['bullet 1', 'bullet 2']::text[]). Concrete, quantified accomplishments and algorithmic features.
- tech_stacks: text[] — CRITICAL: Native PostgreSQL text array (ARRAY['Python', 'Pygame', 'GitLab']::text[]). Languages, libraries, and tools.
- kanji: text — Single thematic Japanese kanji capturing the project's spirit (e.g. '創' Creation, '智' Intelligence, '基' Foundation, '迅' Speed, '網' Network, '墨' Ink, '響' Resonance, '遊' Play).
- image: text — URL to project screenshot (default: './images/sumi-os-workspace.jpg' if none provided).
- github_link: text — GitHub or GitLab repository URL.
- live_link: text — Deployed demo URL or live link.
- start_date: text — Development start period (e.g. 'Jan 2025').
- end_date: text — Development completion period (e.g. 'June 2025' or 'Present').
- is_active: boolean — True if under active development.
- status_label: text — Visual bilingual status pill ('ACTIVE / 稼働中' if active, else 'COMPLETED / 完了').
- is_featured: boolean — Starred for top 3 homepage showcase cards (max 3 featured projects).
- display_order: integer — Sorting position (0, 1, 2...).
- updated_at: timestamptz (Set to NOW())

TABLE 3: public.experience
- id: uuid (PRIMARY KEY) — PostgreSQL UUID. For new entries, use gen_random_uuid().
- title: text — Job title (e.g. 'Barista & Cashier', 'Software Engineering Intern').
- company: text — Commercial employer or organization (e.g. 'Kung Fu Tea', 'Hung Vuong Supermarket').
- location: text — City and state or remote (e.g. 'Philadelphia, PA', 'Remote').
- start_date: text — Start period (e.g. 'Aug 2022').
- end_date: text — End period (e.g. 'Present', 'Dec 2020').
- is_active: boolean — True if currently employed in this role.
- status_label: text — Visual bilingual tenure pill ('ACTIVE / 現職' if current, else '歴任 / COMPLETED').
- kanji: text — Single thematic Japanese kanji representing the organization (e.g. '茶' Tea, '庫' Warehouse/Store, '木' Origin/Craft).
- kanji_subtitle: text — 2 to 5 uppercase characters beneath kanji emblem (e.g. 'TEA', 'STORE', 'AI', 'SYS', 'LOG').
- tags: jsonb — CRITICAL: PostgreSQL JSONB array ('["tag1", "tag2"]'::jsonb). Skills, competencies, and tools.
- overview: text — Summary of the role scope, operating environment, and team context.
- bullets: jsonb — CRITICAL: PostgreSQL JSONB array ('["bullet 1", "bullet 2"]'::jsonb). Quantified responsibilities, optimizations, customer satisfaction, operational metrics.
- description: text — Combined description text fallback.
- logo_url: text — Logo image URL (or empty string '').
- display_order: integer — Sorting order index (0, 1, 2...).
- updated_at: timestamptz (Set to NOW())

TABLE 4: public.philosophy_pillars (Exactly 3 rows: position 1, 2, 3)
- position: integer (PRIMARY KEY) — 1, 2, or 3.
- kanji: text — Single Japanese kanji ('間' Ma, '和' Wa, '匠' Shokunin).
- romaji: text — Japanese romanization ('MA', 'WA', 'SHOKUNIN').
- title: text — English title (e.g. 'Aesthetics of Negative Space', 'Silence & Simple Harmony', 'Artisan Precision & Joinery').
- tag: text — Architectural principle (e.g. 'SUBTRACTIVE SYSTEMS', 'ARCHITECTURAL INTEGRITY', 'RADICAL CRAFT').
- description: text — Narrative paragraph connecting traditional Japanese aesthetic principles to modern high-performance systems engineering.
- updated_at: timestamptz (Set to NOW())

TABLE 5: public.resume_latex (Single row, id = 1)
- id: integer (PRIMARY KEY, always 1)
- latex: text — Full compilation-ready LaTeX source code of Vincent's CV.
- resume_link: text — Public URL to compiled PDF in Supabase Storage.
- content: text — Plain text resume content fallback.
- updated_at: timestamptz (Set to NOW())

================================================================================
3. CRITICAL SQL SYNTAX STANDARDS
================================================================================
1. DOLLAR-QUOTING IS MANDATORY: Always wrap all text strings in dollar quotes ($$...$$) to completely prevent syntax errors with apostrophes, quotes, or newlines.
2. ARRAY SYNTAX RULES:
   - For `projects` (native text[]): Use `ARRAY['item1', 'item2']::text[]`. NEVER use bare JSON brackets like `['a', 'b']`.
   - For `experience` (jsonb): Use `'["item1", "item2"]'::jsonb`.
3. NEVER run DROP, TRUNCATE, ALTER, or unbounded DELETE without a specific WHERE clause.
4. Set `updated_at = NOW()` on all UPDATE and UPSERT operations.

================================================================================
4. FEW-SHOT SQL EXAMPLE GUIDES FOR AI
================================================================================

--- EXAMPLE 1: Upserting a New Project into public.projects ---
```sql
INSERT INTO public.projects (
  id,
  title,
  subtitle,
  category,
  badge,
  overview,
  description,
  bullets,
  tech_stacks,
  kanji,
  image,
  github_link,
  live_link,
  start_date,
  end_date,
  is_active,
  status_label,
  is_featured,
  display_order,
  updated_at
) VALUES (
  $$virtual-pet-machine$$,
  $$Virtual Pet Machine$$,
  $$Web-based interactive state machine running on remote Linux server$$,
  $$SYSTEMS & WEB$$,
  $$SYSTEMS ARCHIVE$$,
  $$Developed an interactive virtual pet simulation modeled as a deterministic finite state machine, handling nested timed state transitions and dynamic user interactions.$$,
  $$Developed an interactive virtual pet simulation modeled as a deterministic finite state machine, handling nested timed state transitions and dynamic user interactions.$$,
  ARRAY[
    $$Engineered a finite state machine in Tranquility to model complex behavioral state transitions$$,
    $$Configured remote SSH sessions on Drexel Tux Linux server for environment deployment and terminal asset editing$$,
    $$Programmed nested temporal timers to govern autonomous mood and vitality degradation$$
  ]::text[],
  ARRAY[$$Tranquility$$, $$HTML$$, $$CSS$$, $$Linux$$, $$SSH$$]::text[],
  $$機$$,
  $$./images/sumi-os-workspace.jpg$$,
  $$https://github.com/VincentYuann$$,
  $$$$,
  $$Dec 2024$$,
  $$Dec 2024$$,
  false,
  $$COMPLETED / 完了$$,
  false,
  2,
  NOW()
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  subtitle = EXCLUDED.subtitle,
  category = EXCLUDED.category,
  badge = EXCLUDED.badge,
  overview = EXCLUDED.overview,
  description = EXCLUDED.description,
  bullets = EXCLUDED.bullets,
  tech_stacks = EXCLUDED.tech_stacks,
  kanji = EXCLUDED.kanji,
  start_date = EXCLUDED.start_date,
  end_date = EXCLUDED.end_date,
  is_active = EXCLUDED.is_active,
  status_label = EXCLUDED.status_label,
  updated_at = NOW();
```

--- EXAMPLE 2: Upserting Work Experience into public.experience ---
```sql
INSERT INTO public.experience (
  id,
  title,
  company,
  location,
  start_date,
  end_date,
  is_active,
  status_label,
  kanji,
  kanji_subtitle,
  tags,
  overview,
  bullets,
  description,
  logo_url,
  display_order,
  updated_at
) VALUES (
  gen_random_uuid(),
  $$Barista & Cashier$$,
  $$Kung Fu Tea$$,
  $$Philadelphia, PA$$,
  $$Aug 2022$$,
  $$Present$$,
  true,
  $$ACTIVE / 現職$$,
  $$茶$$,
  $$TEA$$,
  '["Customer Service", "POS Operations", "Inventory Quality", "Cash Management"]'::jsonb,
  $$High-volume retail beverage operation managing customer satisfaction, customized order accuracy, and financial reconciliation.$$,
  '[
    "Prepare and customize a variety of specialty beverages while maintaining rigorous consistency and quality standards.",
    "Operate POS terminal to handle high-volume sales transactions with zero register discrepancies.",
    "Deliver attentive customer service by resolving order inquiries in a fast-paced retail environment."
  ]'::jsonb,
  $$Prepare beverages, manage POS cash operations, and provide customer service.$$,
  $$$$,
  0,
  NOW()
);
```

--- EXAMPLE 3: Updating Profile Narrative & Capability Pillars ---
```sql
UPDATE public.profile SET
  headline = $$Architecting resilient, local-first intelligence and high-throughput systems.$$,
  tagline = $$Bridging systems engineering with generative AI models and artisanal Japanese-minimalist UI.$$,
  role = $$Full-Stack Software Engineer · Systems & AI$$,
  capability_pillars = '[
    {
      "label": "FULL-STACK & UI",
      "items": "React · TypeScript · Tailwind · Vite",
      "tags": ["React", "TypeScript", "Tailwind", "Vite"]
    },
    {
      "label": "AI & AGENTIC SYSTEMS",
      "items": "Gemini API · Python · FastAPI · RAG",
      "tags": ["Gemini API", "Python", "FastAPI", "RAG"]
    },
    {
      "label": "SYSTEMS INFRASTRUCTURE",
      "items": "PostgreSQL · Docker · Supabase · Linux",
      "tags": ["PostgreSQL", "Docker", "Supabase", "Linux"]
    }
  ]'::jsonb,
  updated_at = NOW()
WHERE id = 1;
```
