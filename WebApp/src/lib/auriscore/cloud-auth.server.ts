import { timingSafeEqual } from "node:crypto";

export function matchesToken(provided: unknown, expected: string | undefined): boolean {
  if (typeof provided !== "string" || !expected || expected.length < 16) return false;
  const actual = Buffer.from(provided), secret = Buffer.from(expected);
  return actual.length === secret.length && timingSafeEqual(actual, secret);
}
