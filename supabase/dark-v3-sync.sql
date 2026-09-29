-- Dark V3 cloud sync backend for Supabase
-- Run this once in Supabase > SQL Editor.

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.pokemon_collections_v3 (
  collection_id text primary key,
  pin_hash text not null,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.pokemon_collections_v3 enable row level security;

revoke all on table public.pokemon_collections_v3 from anon, authenticated;

create or replace function public.load_pokemon_collection_v3(
  p_collection_id text,
  p_pin text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_id text := lower(trim(coalesce(p_collection_id,'')));
  v_row public.pokemon_collections_v3%rowtype;
begin
  if v_id = '' or coalesce(p_pin,'') = '' then
    return jsonb_build_object('ok', false, 'error', 'Collectie-ID en pincode zijn verplicht.');
  end if;

  select * into v_row
  from public.pokemon_collections_v3
  where collection_id = v_id;

  if not found then
    return jsonb_build_object('ok', false, 'error', 'Geen collectie gevonden.');
  end if;

  if extensions.crypt(p_pin, v_row.pin_hash) <> v_row.pin_hash then
    return jsonb_build_object('ok', false, 'error', 'Pincode fout.');
  end if;

  return jsonb_build_object(
    'ok', true,
    'data', coalesce(v_row.data, '{}'::jsonb),
    'updatedAt', v_row.updated_at
  );
end;
$$;

create or replace function public.save_pokemon_collection_v3(
  p_collection_id text,
  p_pin text,
  p_data jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_id text := lower(trim(coalesce(p_collection_id,'')));
  v_hash text;
begin
  if v_id = '' or coalesce(p_pin,'') = '' then
    return jsonb_build_object('ok', false, 'error', 'Collectie-ID en pincode zijn verplicht.');
  end if;

  insert into public.pokemon_collections_v3(collection_id, pin_hash, data, updated_at)
  values (
    v_id,
    extensions.crypt(p_pin, extensions.gen_salt('bf')),
    coalesce(p_data, '{}'::jsonb),
    now()
  )
  on conflict (collection_id) do nothing;

  select pin_hash into v_hash
  from public.pokemon_collections_v3
  where collection_id = v_id;

  if extensions.crypt(p_pin, v_hash) <> v_hash then
    return jsonb_build_object('ok', false, 'error', 'Pincode fout.');
  end if;

  update public.pokemon_collections_v3
  set data = coalesce(p_data, '{}'::jsonb),
      updated_at = now()
  where collection_id = v_id;

  return jsonb_build_object('ok', true);
end;
$$;

revoke all on function public.load_pokemon_collection_v3(text,text) from public;
revoke all on function public.save_pokemon_collection_v3(text,text,jsonb) from public;

grant execute on function public.load_pokemon_collection_v3(text,text) to anon, authenticated;
grant execute on function public.save_pokemon_collection_v3(text,text,jsonb) to anon, authenticated;
