import { deviceAccountAuthorized } from "@/lib/auriscore/device-account.server";

export const runtime = "nodejs";
export async function GET(request: Request) {
  const token = request.headers.get("authorization")?.replace(/^Bearer /, "");
  const allowed = await deviceAccountAuthorized(token);
  return Response.json(allowed ? { available: true, label: "Stetoskop AurisCore" }
    : { error: "Akun belum diberi akses ke alat ini, email belum dikonfirmasi, atau sesi perlu diperbarui." }, {
    status: allowed ? 200 : 403, headers: { "Cache-Control": "no-store" },
  });
}
