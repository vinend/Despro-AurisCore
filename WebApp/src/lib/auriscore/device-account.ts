import { accountClient } from "./account-client";

/** Auth refresh is owned by Supabase. Never store the shared operator secret. */
export async function currentDeviceAccountToken(): Promise<string> {
  const { data, error } = await accountClient().auth.getSession();
  if (error || !data.session) throw new Error("Masuk ke akun AurisCore untuk menghubungkan alat.");
  return data.session.access_token;
}
