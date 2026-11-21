"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import { accountClient, type Profile } from "@/lib/auriscore/account-client";
import { accountFailure } from "@/lib/auriscore/account-feedback";

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
    try {
    const { data, error } = await client.auth.getSession();
    if (error) throw error;
    if (version !== revision.current) return;
    setUser(data.session?.user ?? null);
    setProfile(null);
    if (data.session) {
      const response = await client.from("auriscore_profiles").select("*").eq("user_id", data.session.user.id).maybeSingle();
      if (version !== revision.current) return;
      setProfile(response.data as Profile | null);
    }
    } catch {
      if (version === revision.current) { setUser(null); setProfile(null); }
    } finally {
      if (version === revision.current) setReady(true);
    }
  }, []);
  useEffect(() => {
    if (!configured) return;
    let live = true;
    const initialRefresh = setTimeout(() => { if (live) void refresh(); }, 0);
    const { data } = accountClient().auth.onAuthStateChange(event => {
      if (!live) return;
      if (event === "PASSWORD_RECOVERY") setRecovery(true);
      if (event === "SIGNED_OUT") setRecovery(false);
      // Run queries after the Auth callback releases its session lock.
      setTimeout(() => { if (live) void refresh(); }, 0);
    });
    return () => { live = false; clearTimeout(initialRefresh); data.subscription.unsubscribe(); };
  }, [refresh]);
  return <AccountContext.Provider value={{ user, profile, ready, recovery, finishRecovery: () => setRecovery(false), refresh }}>{children}</AccountContext.Provider>;
}

export function AccountPanel({ presentation = "settings" }: { presentation?: "entry" | "settings" }) {
  const { user, profile, ready, recovery, finishRecovery, refresh } = useAccount();
  const [mode, setMode] = useState<"login" | "signup" | "reset">("login");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [passwordChanged, setPasswordChanged] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);
  const field = "mt-2 min-h-12 w-full rounded-xl border border-border bg-[#fbfcfb] px-3.5 py-3 text-base font-normal transition-shadow placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-emerald-700/25 focus:border-emerald-700";
  if (!configured) return null;
  const profileForm = Boolean(user);
  const changingPassword = recovery && !passwordChanged;
  const Heading = presentation === "entry" ? "h1" : "h2";
  return <section className={presentation === "entry" ? "space-y-6" : "rounded-2xl border bg-white p-4 space-y-4"} aria-label="Akun AurisCore">
    <div className="flex flex-wrap justify-between items-center gap-3">
      <div><Heading className={presentation === "entry" ? "text-2xl font-semibold tracking-tight" : "font-semibold"}>
        {user ? "Akun AurisCore" : mode === "signup" ? "Buat akun Anda" : mode === "reset" ? "Lupa password?" : "Selamat datang kembali"}</Heading>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{user ? `${profile?.name ?? String(user.user_metadata.name ?? "Akun Anda")} · ${user.email}`
          : mode === "signup" ? "Simpan profil dan riwayat pemeriksaan dalam satu akun."
          : mode === "reset" ? "Masukkan email untuk menerima tautan reset password."
          : "Masuk untuk melanjutkan pemeriksaan dan mengakses riwayat Anda."}</p></div>
    </div>
    {!ready && <p role="status">Memuat akun…</p>}
    {ready && (!user || profileForm || changingPassword) && <form ref={formRef} className="space-y-5" key={profile?.user_id ?? mode}
      onSubmit={async event => {
        event.preventDefault(); setBusy(true); setMessage(null); setConfirmEmail(false);
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
            await refresh();
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
        } catch (error) {
          const feedback = accountFailure(error);
          setMessage(feedback.message); setConfirmEmail(feedback.confirmEmail);
        }
        finally { setBusy(false); }
      }}>
      {(profileForm || mode === "signup") && !changingPassword && <div className="grid grid-cols-1 gap-4">
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
      {!profileForm && <div className="grid gap-5">
        {!changingPassword && <label className="block text-sm font-medium">Email<input className={field} type="email" name="email" required autoComplete="email" placeholder="nama@email.com" /></label>}
        {(mode !== "reset" || changingPassword) && <label className="block text-sm font-medium">{changingPassword ? "Password baru" : "Password"}
          <input className={field} type="password" name="password" required minLength={8} maxLength={128}
            placeholder={mode === "signup" || changingPassword ? "Minimal 8 karakter" : "Masukkan password"}
            autoComplete={mode === "signup" || changingPassword ? "new-password" : "current-password"} /></label>}
      </div>}
      {mode === "signup" && <p className="text-sm text-muted-foreground">Profil dan rekaman tersimpan privat di akun. Password minimal 8 karakter.</p>}
      <button disabled={busy} className="min-h-12 w-full rounded-xl bg-emerald-900 px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">
        {busy ? "Memproses…" : changingPassword ? "Simpan password" : profileForm ? "Simpan profil" : mode === "signup" ? "Daftar" : mode === "reset" ? "Kirim tautan reset" : "Masuk"}</button>
    </form>}
    {!user && <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      {(["login", "signup", "reset"] as const).filter(item => item !== mode).map(item =>
        <button key={item} className="min-h-9 rounded-md font-medium text-emerald-800 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700" disabled={busy} onClick={() => { setMode(item); setMessage(null); }}>
          {item === "login" ? "Sudah punya akun? Masuk" : item === "signup" ? "Buat akun" : "Lupa password?"}
        </button>)}
    </div>}
    {message && <p role="status" className="text-sm">{message}</p>}
    {confirmEmail && !user && mode === "login" && <button type="button" disabled={busy}
      className="min-h-11 rounded-xl border border-emerald-800 px-4 py-2 text-sm font-medium text-emerald-900 disabled:opacity-60"
      onClick={async () => {
        const input = formRef.current?.elements.namedItem("email") as HTMLInputElement | null;
        if (!input || !input.reportValidity()) return;
        if (Date.now() < resendAt) { setMessage("Tunggu satu menit sebelum meminta email konfirmasi lagi."); return; }
        setBusy(true); setResendAt(Date.now() + 60_000);
        try {
          const { error } = await accountClient().auth.resend({ type: "signup", email: input.value.trim(),
            options: { emailRedirectTo: window.location.origin } });
          if (error) throw error;
          setMessage("Permintaan konfirmasi dikirim. Periksa inbox dan spam, lalu buka tautan jika email diterima.");
        } catch (error) { setMessage(accountFailure(error).message); }
        finally { setBusy(false); }
      }}>Kirim ulang konfirmasi</button>}
    {user && !profile && <p className="text-sm">Lengkapi profil untuk akun ini.</p>}
  </section>;
}
