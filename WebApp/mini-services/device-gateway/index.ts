import { createDeviceGateway } from "./gateway.ts";
const gateway = createDeviceGateway({ token: process.env.AURISCORE_DEVICE_TOKEN ?? "",
  origins: (process.env.AURISCORE_ALLOWED_ORIGINS ?? "http://localhost:3000").split(",").map(s => s.trim()),
  host: process.env.AURISCORE_GATEWAY_HOST ?? "127.0.0.1", port: Number(process.env.AURISCORE_GATEWAY_PORT ?? "8082") });
console.log("AurisCore device gateway", await gateway.listen());
for (const signal of ["SIGINT", "SIGTERM"] as const) process.once(signal, () => { void gateway.close().then(() => process.exit(0)); });
