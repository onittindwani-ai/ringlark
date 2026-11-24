import assert from "node:assert/strict";
import { test } from "node:test";
import { decodeBytes, detectDelimiter, importBlocker, parseCsv, summariseCsv, toRows } from "./csv.ts";

test("counts data rows and keeps the header out of the count", () => {
  const s = summariseCsv("phone,first_name\n+14155550100,Ann\n+14155550101,Bo\n");
  assert.equal(s.rows, 2);
  assert.deepEqual(s.columns, ["phone", "first_name"]);
  assert.equal(s.hasPhone, true);
});

test("handles quoted commas, doubled quotes, line breaks inside quotes and Windows line ends", () => {
  const rows = parseCsv('email,company\r\na@x.test,"Smith, ""Sons"" & Co"\r\nb@x.test,"two\nlines"\r\n');
  assert.equal(rows[1]![1], 'Smith, "Sons" & Co');
  assert.equal(rows[2]![1], "two\nlines");
  assert.equal(rows.length, 3);
});

test("ignores a byte order mark and blank lines", () => {
  const s = summariseCsv("﻿phone\n\n+14155550100\n\n");
  assert.deepEqual(s.columns, ["phone"]);
  assert.equal(s.rows, 1);
});

test("limits the preview and reports a missing phone column", () => {
  const body = Array.from({ length: 9 }, (_, i) => `n${i}`).join("\n");
  const s = summariseCsv(`name\n${body}\n`);
  assert.equal(s.rows, 9);
  assert.equal(s.preview.length, 5);
  assert.equal(s.hasPhone, false);
});

test("an empty file has no rows", () => {
  assert.deepEqual(summariseCsv(""), { columns: [], rows: 0, preview: [], hasPhone: false });
});

test("reads a semicolon or tab separated file the same way", () => {
  assert.equal(detectDelimiter("first_name;phone\nAnn;+1415"), ";");
  assert.equal(detectDelimiter("first_name\tphone\nAnn\t+1415"), "\t");
  assert.equal(detectDelimiter("first_name,phone\nAnn,+1415"), ",");
  const s = summariseCsv("first_name;phone\nAnn;+14155550100\n");
  assert.deepEqual(s.columns, ["first_name", "phone"]);
  assert.equal(s.hasPhone, true);
  assert.deepEqual(toRows("first_name;phone\nAnn;+14155550100\n"), [{ first_name: "Ann", phone: "+14155550100" }]);
});

test("the import stays blocked for an empty file, a missing phone column and too many people", () => {
  assert.match(importBlocker("")!, /at least one person/);
  assert.match(importBlocker("first_name\nAnn\n")!, /no phone column/);
  const big = "phone\n" + Array.from({ length: 5001 }, (_, i) => `+1415${String(i).padStart(7, "0")}`).join("\n");
  assert.match(importBlocker(big)!, /5001 people/);
  assert.equal(importBlocker("phone\n+14155550100\n"), null);
});

test("a Latin 1 file keeps its accents", () => {
  const latin1 = Uint8Array.from([0x4a, 0x6f, 0x73, 0xe9]); // Jose with an e acute
  assert.equal(decodeBytes(latin1.buffer), "José");
  assert.equal(decodeBytes(new TextEncoder().encode("José").buffer as ArrayBuffer), "José");
});
