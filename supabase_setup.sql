-- Run once in Supabase Dashboard > SQL Editor > New query.
-- Use a fresh Supabase project. This script is safe to re-run: no data is overwritten.

create table if not exists public.budget_settings (
    id integer primary key check (id = 1),
    total_credit numeric(12, 2) not null check (total_credit >= 0),
    opening_used numeric(12, 2) not null check (opening_used >= 0),
    updated_at timestamptz not null default now()
);

create table if not exists public.usage_entries (
    id bigint generated always as identity primary key,
    used_on date not null,
    purpose text not null check (length(trim(purpose)) between 1 and 120),
    amount numeric(12, 2) not null check (amount > 0),
    created_at timestamptz not null default now()
);

create index if not exists usage_entries_used_on_idx
    on public.usage_entries (used_on desc);

-- Opening amount already used (not itemized); dated transactions start empty.
insert into public.budget_settings (id, total_credit, opening_used)
values (1, 340000.00, 20000.00)
on conflict (id) do nothing;

-- Nobody using a public/publishable key may query or change this family ledger.
-- The server-side Supabase SECRET key bypasses RLS; keep it in Streamlit Secrets only.
alter table public.budget_settings enable row level security;
alter table public.usage_entries enable row level security;

revoke all on table public.budget_settings from anon, authenticated;
revoke all on table public.usage_entries from anon, authenticated;

grant all on table public.budget_settings to service_role;
grant all on table public.usage_entries to service_role;
grant all on sequence public.usage_entries_id_seq to service_role;

-- Intentionally NO RLS policies for anon/authenticated.
-- The Streamlit server enforces separate owner vs. viewer passwords.
