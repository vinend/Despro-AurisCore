/** Publish batches through the HTTPS API of the same Redis instance as the subscriber. */
export function createRedisAudioPublisher(redisUrl: string, restUrl: string, token: string) {
  const endpoint = new URL(restUrl);
  if (endpoint.protocol !== "https:" || endpoint.hostname !== new URL(redisUrl).hostname
    || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || !token) {
    throw new Error("Redis audio endpoint is misconfigured");
  }
  const pipeline = new URL("/pipeline", endpoint);
  return async (commands: (string | number)[][]): Promise<number[]> => {
    const response = await fetch(pipeline, {
      method: "POST", redirect: "error", cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(commands),
    });
    if (!response.ok) throw new Error(response.status === 429 ? "Redis request limit" : "Redis publish failed");
    const values: unknown = await response.json();
    if (!Array.isArray(values) || values.length !== commands.length
      || values.some(value => typeof value?.result !== "number")) {
      throw new Error("Invalid Redis publish response");
    }
    return values.map(value => value.result);
  };
}
