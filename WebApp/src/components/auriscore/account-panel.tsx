"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import { accountClient, type Profile } from "@/lib/auriscore/account-client";

const configured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
type Account = { user: User | null; profile: Profile | null; ready: boolean; recovery: boolean; finishRecovery: () => void; refresh: () => Promise<void> };
const AccountContext = createContext<Account>({ user: null, profile: null, ready: !configured, recovery: false, finishRecovery: () => {}, refresh: async () => {} });
export const useAccount = () => useContext(AccountContext);

export function AccountProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [ready, setReady] = useState(!configured);
  const [recovery, setRecovery] = useState(false);
  const revision = useRef(0);
  const refresh = useCallback(async () => {
    if (!configured) return;
    const version = ++revision.current;
    const client = accountClient();
    const { data } = await client.auth.getSession();
    if (version !== revision.current) return;
    setUser(data.session?.user ?? null);
    setProfile(null);
    if (data.session) {
      const response = await client.from("auriscore_profiles").select("*").eq("user_id", data.session.user.id).maybeSingle();
      if (version !== revision.current) return;
      setProfile(response.data as Profile | null);
    }
    setReady(true);
  }, []);
  useEffect(() => {
    if (!configured) return;
    let live = true;
    void refresh();
    const { data } = accountClient().auth.onAuthStateChange(event => {
      if (!live) return;
      if (event === "PASSWORD_RECOVERY") setRecovery(true);
      if (event === "SIGNED_OUT") setRecovery(false);
      // Run queries after the Auth callback releases its session lock.
      setTimeout(() => { if (live) void refresh(); }, 0);
    });
    return () => { live = false; data.subscription.unsubscribe(); };
  }, [refresh]);
  return <AccountContext.Provider value={{ user, profile, ready, recovery, finishRecovery: () => setRecovery(false), refresh }}>{children}</AccountContext.Provider>;
}

export function AccountPanel({ defaultEditing = false }: { defaultEditing?: boolean }) {
  const { user, profile, ready, recovery, finishRecovery, refresh } = useAccount();
  const [mode, setMode] = useState<"login" | "signup" | "reset">("login");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState(defaultEditing);
  const [passwordChanged, setPasswordChanged] = useState(false);
  const field = "min-h-11 rounded-lg border border-border bg-white px-3 py-2 w-full";
  if (!configured) return null;
  const profileForm = user && (!profile || editing);
  const changingPassword = recovery && !passwordChanged;
  return <section className="rounded-2xl border bg-white p-4 space-y-3" aria-label="Akun AurisCore">
    <div className="flex flex-wrap justify-between items-center gap-3">
      <div><h2 className="font-semibold">Akun AurisCore</h2>
        <p className="text-sm text-muted-foreground">{user ? `${profile?.name ?? user.email} · ${user.email}`
          : "Masuk untuk menyimpan profil, hasil analisis, dan rekaman di perangkat lain."}</p></div>
      {user && <div className="flex gap-2">
        <button className="border rounded-lg px-3 py-2" disabled={busy} onClick={() => setEditing(value => !value)}>Edit profil</button>
        <button className="border rounded-lg px-3 py-2" disabled={busy} onClick={async () => {
          setBusy(true);
          const { error } = await accountClient().auth.signOut({ scope: "local" });
          setMessage(error ? "Keluar belum berhasil. Coba lagi." : null);
          await refresh(); setBusy(false);
        }}>Keluar</button>
      </div>}
    </div>
    {!ready && <p role="status">Memuat akun…</p>}
    {ready && (!user || profileForm || changingPassword) && <form className="space-y-3" key={profile?.user_id ?? mode}
      onSubmit={async event => {
        event.preventDefault(); setBusy(true); setMessage(null);
        const form = new FormData(event.currentTarget);
        const email = String(form.get("email") ?? "").trim();
        const password = String(form.get("password") ?? "");
        try {
          const client = accountClient();
          if (changingPassword) {
            const { error } = await client.auth.updateUser({ password });
            if (error) throw error;
            setPasswordChanged(true); finishRecovery(); setMessage("Password diperbarui.");
          } else if (profileForm) {
            const row: Profile = { user_id: user!.id, name: String(form.get("name")).trim(),
              date_of_birth: String(form.get("date_of_birth")), gender: String(form.get("gender")) as Profile["gender"] };
            const { error } = await client.from("auriscore_profiles").upsert({ ...row, updated_at: new Date().toISOString() });
            if (error) throw error;
            if (email && email !== user!.email) {
              const { error: emailError } = await client.auth.updateUser({ email }, { emailRedirectTo: window.location.origin + "/settings" });
              if (emailError) {
                await refresh();
                setMessage("Profil tersimpan, tetapi perubahan email belum berhasil. Coba lagi nanti.");
                return;
              }
            }
            await refresh(); setEditing(false);
            setMessage(email && email !== user!.email
              ? "Profil tersimpan. Permintaan perubahan email dikirim; selesaikan konfirmasi pada email lama dan/atau baru sesuai pengaturan akun."
              : "Profil tersimpan.");
          } else if (mode === "signup") {
            const { error } = await client.auth.signUp({ email, password, options: {
              emailRedirectTo: window.location.origin,
              data: { name: String(form.get("name")).trim(), date_of_birth: String(form.get("date_of_birth")), gender: String(form.get("gender")) },
            } });
            if (error) throw error;
            setMessage("Cek email untuk konfirmasi akun, lalu masuk di sini."); setMode("login");
          } else if (mode === "reset") {
            const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
            if (error) throw error;
            setMessage("Jika email terdaftar, tautan reset password akan dikirim.");
          } else {
            const { error } = await client.auth.signInWithPassword({ email, password });
            if (error) throw error;
            await refresh();
          }
        } catch { setMessage("Belum berhasil. Periksa data, konfirmasi email, dan koneksi. Coba lagi beberapa saat."); }
        finally { setBusy(false); }
      }}>
      {(profileForm || mode === "signup") && !changingPassword && <div className="grid gap-3 sm:grid-cols-3">
        <label>Nama<input className={field} name="name" required maxLength={120}
          autoComplete="name" defaultValue={profile?.name ?? String(user?.user_metadata.name ?? "")} /></label>
        <label>Tanggal lahir<input className={field} type="date" name="date_of_birth" required min="1900-01-01"
          max={new Date().toISOString().slice(0, 10)} defaultValue={profile?.date_of_birth ?? String(user?.user_metadata.date_of_birth ?? "")} /></label>
        <label>Gender<select className={field} name="gender" required defaultValue={profile?.gender ?? String(user?.user_metadata.gender ?? "prefer_not_to_say")}>
          <option value="female">Perempuan</option><option value="male">Laki-laki</option>
          <option value="other">Lainnya</option><option value="prefer_not_to_say">Tidak ingin menyebutkan</option>
        </select></label>
      </div>}
      {profileForm && !changingPassword && <label className="block">Email
        <input className={field} type="email" name="email" required autoComplete="email" defaultValue={user?.email ?? ""} />
        <span className="mt-1 block text-sm text-muted-foreground">Perubahan email memerlukan konfirmasi melalui email.</span>
      </label>}
      {!profileForm && <div className="grid gap-3 sm:grid-cols-2">
        {!changingPassword && <label>Email<input className={field} type="email" name="email" required autoComplete="email" /></label>}
        {(mode !== "reset" || changingPassword) && <label>{changingPassword ? "Password baru" : "Password"}
          <input className={field} type="password" name="password" required minLength={8} maxLength={128}
            autoComplete={mode === "signup" || changingPassword ? "new-password" : "current-password"} /></label>}
      </div>}
      {mode === "signup" && <p className="text-sm text-muted-foreground">Profil dan rekaman tersimpan privat di akun. Password minimal 8 karakter.</p>}
      <button disabled={busy} className="bg-emerald-800 text-white rounded-lg px-4 py-2">
        {busy ? "Memproses…" : changingPassword ? "Simpan password" : profileForm ? "Simpan profil" : mode === "signup" ? "Daftar" : mode === "reset" ? "Kirim tautan reset" : "Masuk"}</button>
    </form>}
    {!user && <div className="flex flex-wrap gap-4 text-sm">
      {(["login", "signup", "reset"] as const).filter(item => item !== mode).map(item =>
        <button key={item} className="underline" disabled={busy} onClick={() => { setMode(item); setMessage(null); }}>
          {item === "login" ? "Sudah punya akun? Masuk" : item === "signup" ? "Buat akun" : "Lupa password?"}
        </button>)}
    </div>}
    {message && <p role="status" className="text-sm">{message}</p>}
    {user && !profile && <p className="text-sm">Lengkapi profil untuk akun ini.</p>}
  </section>;
}
