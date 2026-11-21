import { createHash } from "node:crypto";

// This deployment owns one gateway namespace/device. Factory/operator assignment
// stays server-side; creating an account never grants access to a stethoscope.
const grants = new Map<string, number>();
export async function deviceAccountAuthorized(token: unknown): Promise<boolean> {
  if (typeof token !== "string" || token.length > 8192 || token.split(".").length !== 3) return false;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  const assigned = (process.env.AURISCORE_DEVICE_ACCOUNT_EMAILS ?? "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
  if (!url?.startsWith("https://") || !key || !assigned.length) return false;
  const hash = createHash("sha256").update(JSON.stringify([url, assigned, token])).digest("hex");
  if ((grants.get(hash) ?? 0) > Date.now()) return true;
  try {
    const response = await fetch(new URL("/auth/v1/user", url), { headers: {
      apikey: key, Authorization: `Bearer ${token}`,
    }, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(4000) });
    if (!response.ok) return false;
    const user = await response.json();
    if (typeof user.id !== "string" || !user.email_confirmed_at || typeof user.email !== "string"
        || !assigned.includes(user.email.toLowerCase())) return false;
    // Decode expiry only after the provider has verified the complete JWT.
    const { exp } = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString());
    if (typeof exp !== "number" || !Number.isFinite(exp) || exp * 1000 <= Date.now()) return false;
    if (grants.size >= 64) grants.delete(grants.keys().next().value!);
    grants.set(hash, Math.min(Date.now() + 30_000, exp * 1000));
    return true;
  } catch { return false; }
}
