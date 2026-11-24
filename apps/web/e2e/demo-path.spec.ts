import { expect, test } from "@playwright/test";
import { call, login, resetDemo, watch } from "./helpers";

test("the whole demo path: run, watch a call, scrub a call, edit and test a prompt, tick the checklist, kill switch, approve a follow up", async ({ page }) => {
  const errors = watch(page);
  await login(page);
  await resetDemo(page);

  // 1. The overview shows the safety state and history, then Run now places demo calls.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Safe to dial?" })).toBeVisible();
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText(/Ran every job. Placed \d+ demo calls/)).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Held back by the rules" })).toBeVisible();
  await expect(page.getByText("Closed in their time zone", { exact: true })).toBeVisible();
  await expect(page.getByText("On the do not call list", { exact: true })).toBeVisible();

  // 2. Live console: pick a booked call, play it at 4x, the transcript streams and the state ends.
  await page.goto("/live");
  await expect(page.getByRole("heading", { name: "Live console" })).toBeVisible();
  await expect(page.getByText("Replay of a recorded demo call")).toBeVisible();
  await page.getByRole("radio", { name: "4x" }).click();
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("status").filter({ hasText: /speaking|Caller speaking/ }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Transcript").getByText("AI assistant").first()).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Ended" }).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Take over" }).click();
  await page.getByRole("button", { name: "Take over" }).last().click();
  await expect(page.getByText(/Practice run/)).toBeVisible(); // the Live console replays a finished demo call, so this is a practice run

  // 3. Call log: filter to booked, open one, drag the scrubber, the transcript follows.
  await page.goto("/calls");
  await page.getByLabel("Outcome").selectOption("booked");
  await expect(page.getByRole("grid", { name: "Calls" })).toBeVisible();
  await page.getByRole("grid", { name: "Calls" }).focus();
  await page.keyboard.press("j");
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByLabel("Call position")).toBeVisible();
  await sheet.getByLabel("Call position").fill("9000");
  await expect(sheet.locator('[data-current="true"]')).toHaveCount(1);
  await expect(sheet.getByText("Said it is an AI")).toBeVisible();
  await page.keyboard.press("Escape");

  // 4. Agents: edit a prompt (new version), see the diff, run the persona suite.
  await page.goto("/agents");
  const ta = page.getByLabel(/^Prompt \(version/);
  const text = await ta.inputValue();
  await ta.fill(text + "\n- Always thank the person for their time.");
  await page.getByRole("button", { name: "Save as a new version" }).click();
  await expect(page.getByText(/Saved as version 3/)).toBeVisible();
  await expect(page.getByText("Version 3").first()).toBeVisible();
  await page.getByRole("tab", { name: "Simulator and persona suite" }).click();
  await page.getByRole("button", { name: /Run this caller/ }).click();
  await expect(page.getByText("offline stand in made of rules, not a language model")).toBeVisible();
  await page.getByRole("button", { name: /Run the suite on version/ }).click();
  await expect(page.getByText("14 of 14 passed")).toBeVisible();
  await expect(page.getByText("offline rules, not a language model").first()).toBeVisible();

  // 5. Numbers and compliance: tick a step, add a number to the do not call list.
  await page.goto("/numbers");
  await page.getByRole("checkbox").first().click();
  await expect(page.getByText(/1 of 5 steps done/).or(page.getByText(/2 of 5 steps done/)).first()).toBeVisible();
  await page.getByLabel("Add a number").fill("+14155550177");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(/Added. This number will never be called/)).toBeVisible();

  // 6. Follow ups: approve one.
  await page.goto("/followups");
  await expect(page.getByRole("tab", { name: /Approvals/ })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText(/Approved. It is sent on the next run/)).toBeVisible();

  // 7. The kill switch stops dialling.
  await page.goto("/");
  await page.getByRole("button", { name: "Pause all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Pause all" }).click();
  await expect(page.getByText("Kill switch is on.")).toBeVisible();
  const r = await call(page, "/demo/tick");
  expect((await r.json()).dial.halted).toBe(true);
  await page.getByRole("status").getByRole("button", { name: "Turn it off" }).click();
  await expect(page.getByText("Kill switch is on.")).toHaveCount(0);

  expect(errors.filter((e) => !/favicon/.test(e)), errors.join("\n")).toEqual([]);
});

test("force draft: nothing is dialled, drafts are saved, and the API cannot turn live on", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await call(page, "/settings", { force_draft: true });
  const r = await (await call(page, "/demo/tick")).json();
  expect(r.dial.placed).toBe(0);
  expect(r.dial.drafted).toBeGreaterThan(0);
  await page.goto("/");
  await expect(page.getByText("Draft mode.", { exact: true })).toBeVisible();
  const s = await (await call(page, "/settings", { force_draft: false })).json();
  expect(s.effective_mode).toBe("live");
});
