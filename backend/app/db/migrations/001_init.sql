-- MIMIC × GhostQA initial schema. Paste into Supabase → SQL Editor → Run.
-- Backend uses the service-role key only; RLS is on with no policies, so anon/public access is denied.

create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  target_url text not null,
  goal text not null,
  success_criteria jsonb,
  status text not null,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  metrics jsonb,
  error text
);

create table if not exists personas (
  run_id uuid not null references runs(id) on delete cascade,
  id text not null,
  persona_type text not null,
  config jsonb not null,
  state jsonb not null,
  outcome text,
  primary key (run_id, id)
);

create table if not exists events (
  run_id uuid not null references runs(id) on delete cascade,
  seq int not null,
  persona_id text,
  ts timestamptz not null,
  type text not null,
  step int,
  url text,
  payload jsonb not null default '{}'::jsonb,
  primary key (run_id, seq)
);
create index if not exists events_run_persona_seq on events (run_id, persona_id, seq);

create table if not exists findings (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references runs(id) on delete cascade,
  category text not null,
  severity text,
  page text,
  personas text[] not null,
  evidence jsonb not null,
  observed text not null,
  interpretation text,
  suggested_investigation text,
  source text not null
);

-- Gemini quota tracking: every request sent counts (503s included).
create table if not exists gemini_usage (
  key_hash text not null,
  model text not null,
  day date not null,
  count int not null default 0,
  primary key (key_hash, model, day)
);

create or replace function increment_gemini_usage(p_key_hash text, p_model text, p_day date)
returns int language sql as $$
  insert into gemini_usage (key_hash, model, day, count) values (p_key_hash, p_model, p_day, 1)
  on conflict (key_hash, model, day) do update set count = gemini_usage.count + 1
  returning count;
$$;

alter table runs enable row level security;
alter table personas enable row level security;
alter table events enable row level security;
alter table findings enable row level security;
alter table gemini_usage enable row level security;

-- Private bucket for screenshots (served to the frontend via signed URLs).
insert into storage.buckets (id, name, public)
values ('screenshots', 'screenshots', false)
on conflict (id) do nothing;
