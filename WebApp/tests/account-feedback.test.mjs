import test from "node:test";
import assert from "node:assert/strict";
import { accountFailure } from "../src/lib/auriscore/account-feedback.ts";

test("unconfirmed email leads to confirmation, credentials do not enumerate accounts", () => {
  assert.equal(accountFailure({code:"email_not_confirmed"}).confirmEmail, true);
  const result = accountFailure({code:"invalid_credentials"});
  assert.equal(result.confirmEmail, false);
  assert.match(result.message, /Email atau password tidak cocok/);
  assert.match(result.message, /Buat akun/);
});
test("network, rate limit and unavailable email delivery have distinct recovery guidance", () => {
  assert.match(accountFailure({status:429}).message, /Tunggu/);
  assert.match(accountFailure({name:"AuthRetryableFetchError"}).message, /internet/);
  assert.match(accountFailure({code:"email_address_not_authorized"}).message, /Pengelola/);
  assert.match(accountFailure({code:"weak_password"}).message, /lebih kuat/);
});
test("provider text and unknown errors never echo credentials or internal details", () => {
  for (const error of [null, undefined, new Error("SECRET"), {code:"unknown",message:"SECRET"}, "SECRET"])
    assert.doesNotMatch(accountFailure(error).message, /SECRET/);
});
