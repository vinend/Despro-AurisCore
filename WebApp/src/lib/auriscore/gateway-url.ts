/** LAN clients use the website's host, never the phone's own localhost. */
export function defaultGatewayUrl(location: { protocol: string; hostname: string; host?: string }): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  if (location.protocol === "https:") return `${scheme}//${location.host ?? location.hostname}/browser`;
  return `${scheme}//${location.hostname}:8082/browser`;
}
