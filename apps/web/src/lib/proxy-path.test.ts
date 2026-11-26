import assert from "node:assert/strict";
import { test } from "node:test";
import { forwardPath, visitorAddress } from "./proxy-path.ts";

test("pages the app uses are forwarded", () => {
  assert.equal(forwardPath(["calls"]), "calls");
  assert.equal(forwardPath(["campaigns", "3", "targets"]), "campaigns/3/targets");
  assert.equal(forwardPath(["auth", "me"]), "auth/me");
  assert.equal(forwardPath(["events", "stream"]), "events/stream");
});

test("sign in, webhooks, tools and the private pages are refused", () => {
  for (const p of [["auth", "login"], ["webhooks", "telnyx"], ["tools", "1", "end_call"], ["health"], ["docs"], ["openapi.json"], ["auth"]]) assert.equal(forwardPath(p), null, p.join("/"));
});

test("dots, encoded slashes and percent signs cannot reach another path", () => {
  for (const p of [["calls", "..", "tools", "1", "end_call"], ["calls/../tools/1/end_call"], ["..", "..", "health"], ["calls", "%2e%2e"], ["calls\\..\\tools"], [".", "calls"], ["calls", ""]]) assert.equal(forwardPath(p), null, p.join("|"));
});

test("only the last address of x-forwarded-for is trusted", () => {
  assert.equal(visitorAddress("203.0.113.9"), "203.0.113.9");
  assert.equal(visitorAddress("1.2.3.4, 10.0.0.7, 198.51.100.2"), "198.51.100.2");
  assert.equal(visitorAddress("1.2.3.4, <script>"), "");
  assert.equal(visitorAddress(null), "");
});
