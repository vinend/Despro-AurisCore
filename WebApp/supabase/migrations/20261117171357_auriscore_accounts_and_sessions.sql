begin;

create table public.auriscore_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 120),
  date_of_birth date not null check (date_of_birth between date '1900-01-01' and current_date),
  gender text not null check (gender in ('female', 'male', 'other', 'prefer_not_to_say')),
  updated_at timestamptz not null default now()
);

create table public.auriscore_sessions (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  recorded_at timestamptz not null,
  created_at timestamptz not null default now(),
  mode text not null check (mode in ('heart','lung','abdomen')),
  source text not null check (length(source) between 1 and 64),
  duration_ms integer not null check (duration_ms between 1 and 120000),
  result jsonb not null check (
    jsonb_typeof(result) = 'object'
    and (result->>'schema_version' = 'organ-analysis-v1') is true
    and (result->>'mode' = mode) is true
    and octet_length(result::text) <= 1048576
  ),
  audio_path text not null unique,
  audio_sha256 text not null check (audio_sha256 ~ '^[0-9a-f]{64}$'),
  audio_bytes integer not null check (audio_bytes between 44 and 4194304),
  sync_state text not null default 'uploading' check (sync_state in ('uploading','ready')),
  constraint owned_audio_path check (audio_path = user_id::text || '/' || id::text || '.wav')
);
create index auriscore_sessions_owner_time on public.auriscore_sessions(user_id, recorded_at desc, id desc);

alter table public.auriscore_profiles enable row level security;
alter table public.auriscore_sessions enable row level security;
revoke all on public.auriscore_profiles, public.auriscore_sessions from anon, authenticated;
grant select, insert, update on public.auriscore_profiles to authenticated;
grant select, insert on public.auriscore_sessions to authenticated;
grant update(sync_state) on public.auriscore_sessions to authenticated;

create policy profiles_select_self on public.auriscore_profiles for select to authenticated
  using ((select auth.uid()) = user_id);
create policy profiles_insert_self on public.auriscore_profiles for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy profiles_update_self on public.auriscore_profiles for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy sessions_select_self on public.auriscore_sessions for select to authenticated
  using ((select auth.uid()) = user_id);
create policy sessions_insert_self on public.auriscore_sessions for insert to authenticated
  with check ((select auth.uid()) = user_id and sync_state = 'uploading');
create policy sessions_finish_upload on public.auriscore_sessions for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and sync_state = 'ready' and exists (
    select 1 from storage.objects o where o.bucket_id = 'auriscore-recordings' and o.name = audio_path
  ));

insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('auriscore-recordings','auriscore-recordings',false,4194304,array['audio/wav']);

create policy audio_select_self on storage.objects for select to authenticated
  using (bucket_id = 'auriscore-recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy audio_insert_self on storage.objects for insert to authenticated
  with check (bucket_id = 'auriscore-recordings' and (storage.foldername(name))[1] = (select auth.uid())::text
    and exists (select 1 from public.auriscore_sessions s where s.user_id = (select auth.uid())
      and s.audio_path = name and s.sync_state = 'uploading'));

commit;
