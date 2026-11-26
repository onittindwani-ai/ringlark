import assert from "node:assert/strict";
import { test } from "node:test";
import { QA_PAGE, hasMore, qaPageUrl } from "./qa-paging.ts";

test("each page asks for one page with its own offset, never a growing limit", () => {
  assert.equal(qaPageUrl("open", 0), "/qa?show=open&limit=100&offset=0");
  assert.equal(qaPageUrl("all", 11), "/qa?show=all&limit=100&offset=1100");
  for (let p = 0; p < 200; p++) assert.ok(QA_PAGE <= 1000 && Number(new URL(`http://x${qaPageUrl("open", p)}`).searchParams.get("limit")) <= 1000);
});

test("a bad page number is read as the first page", () => {
  assert.equal(qaPageUrl("open", -3), "/qa?show=open&limit=100&offset=0");
  assert.equal(qaPageUrl("open", 1.5), "/qa?show=open&limit=100&offset=0");
});

test("a full page means there may be more", () => {
  assert.equal(hasMore(100), true);
  assert.equal(hasMore(99), false);
  assert.equal(hasMore(0), false);
});
