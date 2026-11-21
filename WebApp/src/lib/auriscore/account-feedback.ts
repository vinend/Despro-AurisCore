/** Safe, actionable Auth messages. Never display provider messages or credentials. */
export function accountFailure(error: unknown): { message: string; confirmEmail: boolean } {
  const value = error && typeof error === "object" ? error as { code?: unknown; status?: unknown; name?: unknown } : {};
  const code = typeof value.code === "string" ? value.code : "";
  if (code === "email_not_confirmed") return {
    message: "Email belum dikonfirmasi. Buka tautan konfirmasi pada email pendaftaran. Jika belum diterima, gunakan Kirim ulang konfirmasi.", confirmEmail: true,
  };
  if (code === "invalid_credentials") return {
    message: "Email atau password tidak cocok. Jika belum pernah mendaftar AurisCore, pilih Buat akun. Akses Vercel memakai akun yang berbeda.", confirmEmail: false,
  };
  if (["over_request_rate_limit", "over_email_send_rate_limit"].includes(code) || value.status === 429)
    return { message: "Terlalu banyak percobaan atau pengiriman email. Tunggu beberapa saat sebelum mencoba lagi.", confirmEmail: false };
  if (code === "email_address_not_authorized") return {
    message: "Layanan email belum mengizinkan pengiriman ke alamat ini. Pengelola perlu menyiapkan pengiriman email AurisCore.", confirmEmail: false,
  };
  if (code === "signup_disabled" || code === "email_provider_disabled") return {
    message: "Layanan pendaftaran atau login email belum diaktifkan. Hubungi pengelola AurisCore.", confirmEmail: false,
  };
  if (code === "weak_password") return { message: "Password belum memenuhi ketentuan keamanan. Gunakan password yang lebih kuat.", confirmEmail: false };
  if (["otp_expired", "flow_state_expired", "flow_state_not_found"].includes(code)) return {
    message: "Tautan konfirmasi atau pemulihan sudah tidak berlaku. Minta tautan baru dan buka di browser yang sama.", confirmEmail: false,
  };
  if (value.status === 0 || value.name === "AuthRetryableFetchError" || value.name === "TypeError") return {
    message: "Layanan akun tidak dapat dijangkau. Periksa internet lalu coba lagi.", confirmEmail: false,
  };
  return { message: "Layanan akun belum dapat menyelesaikan permintaan. Coba lagi beberapa saat; jika berulang, hubungi pengelola.", confirmEmail: false };
}
