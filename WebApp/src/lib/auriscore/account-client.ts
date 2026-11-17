"use client";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;
export function accountClient(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("Layanan akun belum dikonfigurasi.");
  client ??= createClient(url, key);
  return client;
}

export type Profile = {
  user_id: string;
  name: string;
  date_of_birth: string;
  gender: "female" | "male" | "other" | "prefer_not_to_say";
};
