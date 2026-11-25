import assert from "node:assert/strict";
import { test } from "node:test";
import { afterSignIn } from "./next-path.ts";

const O = "https://app.example.test";

test("a path on this site is kept", () => {
  assert.equal(afterSignIn("?next=%2Fcalls%3Fq%3D1", O), "/calls?q=1");
  assert.equal(afterSignIn("", O), "/");
});

test("anything that lands on another site is dropped", () => {
  for (const next of ["//evil.example", "/\t/evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)", "/\n/evil.example"]) {
    assert.equal(afterSignIn(`?next=${encodeURIComponent(next)}`, O), "/", next);
  }
});
