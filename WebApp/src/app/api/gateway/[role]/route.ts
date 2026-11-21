import { upgradeWebSocket } from "@vercel/functions";
import { attachCloudSocket } from "@/lib/auriscore/cloud-gateway.server";
import { deviceAccountAuthorized } from "@/lib/auriscore/device-account.server";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(request: Request, context: { params: Promise<{ role: string }> }) {
  const { role } = await context.params;
  if (role !== "device" && role !== "browser") return new Response(null, { status: 404 });
  const url = process.env.AURISCORE_REDIS_URL;
  const namespace = process.env.AURISCORE_CLOUD_NAMESPACE;
  const deviceToken = process.env.AURISCORE_DEVICE_TOKEN;
  const operatorToken = process.env.AURISCORE_OPERATOR_TOKEN;
  const origin = process.env.AURISCORE_BROWSER_ORIGIN;
  if (!url?.startsWith("rediss://") || !namespace || !/^[\w-]{1,64}$/.test(namespace)
    || !deviceToken || deviceToken.length < 16 || !operatorToken || operatorToken.length < 16
    || deviceToken === operatorToken || !origin)
    return new Response(null, { status: 503 });
  if (role === "browser" && request.headers.get("origin") !== origin) return new Response(null, { status: 403 });
  if (request.headers.get("upgrade")?.toLowerCase() !== "websocket") return new Response(null, { status: 426 });
  return upgradeWebSocket(ws => attachCloudSocket(ws, role, {
    url, namespace, token: role === "device" ? deviceToken : operatorToken,
    authorize: role === "browser" ? deviceAccountAuthorized : undefined,
  }), { maxPayload: 2048 });
}
