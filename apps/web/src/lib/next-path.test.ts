import assert from "node:assert/strict";
import { test } from "node:test";
import { afterSignIn } from "./next-path.ts";

const O = "https://app.example.test";

test("a path on this site is kept", () => {
  assert.equal(afterSignIn("?next=%2Fcalls%3Fq%3D1", O), "/calls?q=1");
  assert.equal(afterSignIn("", O), "/");
  assert.equal(afterSignIn(`?next=${encodeURIComponent("/campaigns/3?tab=targets#top")}`, O), "/campaigns/3?tab=targets#top");
  assert.equal(afterSignIn(`?next=${encodeURIComponent("/a/../calls")}`, O), "/calls");
});

test("anything that lands on another site is dropped", () => {
  for (const next of ["//evil.example", "/\t/evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)", "/\n/evil.example"]) {
    assert.equal(afterSignIn(`?next=${encodeURIComponent(next)}`, O), "/", next);
  }
});

test("dot segments that resolve to another site are dropped (the check runs on the resolved address)", () => {
  for (const next of ["/a/..//evil.example", "/a/%2e%2e//evil.example", "/a/%2E%2E//evil.example", "/.//evil.example", "/..//evil.example", "/a/./..//evil.example/x", "/a/..\\/evil.example"]) {
    const out = afterSignIn(`?next=${encodeURIComponent(next)}`, O);
    assert.equal(out, "/", next);
  }
});

test("whatever comes back is a path that stays on this site", () => {
  for (const next of ["/a/..//evil.example", "/x//y", "/%2f/evil.example", "/ok?next=//evil.example", "/a/b/../../c"]) {
    const out = afterSignIn(`?next=${encodeURIComponent(next)}`, O);
    assert.ok(out.startsWith("/") && !out.startsWith("//") && !out.startsWith("/\\"), `${next} -> ${out}`);
    assert.equal(new URL(out, O).origin, O, next);
  }
});
