import { expect, test, type Page } from "@playwright/test";
import { call, login, resetDemo, runDays, watch } from "./helpers";

/** Failures the second walk through every screen found. Each test is one defect. */

async function sampleNumbers(page: Page, ms = 2500): Promise<string[]> {
  return page.evaluate((span) => new Promise<string[]>((done) => {
    const seen = new Set<string>();
    const read = () => document.querySelectorAll(".rm-big [aria-hidden], .sx-stat__value [aria-hidden]").forEach((e) => seen.add((e.textContent ?? "").trim()));
    const timer = setInterval(read, 30);
    setTimeout(() => { clearInterval(timer); done([...seen]); }, span);
  }), ms);
}

test.describe("round 5, second walk", () => {
  test("the animated overview numbers never show decimals on the way up, after load and after a reset", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 1);
    await page.goto("/");
    const first = await sampleNumbers(page);
    expect(first.length).toBeGreaterThan(4); // it really was counting
    await call(page, "/demo/reset");
    await page.reload();
    const second = await sampleNumbers(page);
    // The page is open while the demo is reset from the palette: the numbers count to the new values without a reload.
    await page.keyboard.press("Meta+k"); await page.keyboard.type("reset"); await page.keyboard.press("Enter");
    await page.getByRole("dialog").getByRole("button", { name: "Reset" }).click();
    const third = await sampleNumbers(page);
    for (const text of [...first, ...second, ...third]) expect(text, `sampled "${text}"`).toMatch(/^\d[\d,]*%?$/);
  });

  test("a person who already booked, finished, or sits in a campaign that is not running is not listed as callable", async ({ page }) => {
    await login(page); await resetDemo(page);
    await page.goto("/campaigns");
    await expect(page.getByRole("grid", { name: /Targets of/ })).toContainText("Already booked, no more calls");
    await expect(page.getByRole("grid", { name: /Targets of/ })).toContainText("Finished, no more calls");
    await page.getByRole("button", { name: "New campaign" }).click();
    await page.getByRole("dialog").getByLabel("Name").fill("Not started yet");
    await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
    await page.getByRole("button", { name: "Import" }).nth(1).click();
    await page.getByLabel("Or paste CSV text").fill("phone,timezone\n+14155551234,America/New_York");
    await page.getByRole("dialog").getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByText(/Imported 1 person\./)).toBeVisible();
    await page.getByRole("button", { name: "Show people" }).nth(1).click();
    await expect(page.getByRole("grid", { name: /Not started yet/ })).not.toContainText("Can be called now");
  });

  test("the prompt versions table shows the agent and the number of calls", async ({ page }) => {
    await login(page); await resetDemo(page);
    await page.goto("/metrics");
    const grid = page.getByRole("grid", { name: "Prompt versions" });
    await expect(grid.getByRole("row").filter({ hasText: "v2" })).toContainText("Casey");
    await expect(grid.getByRole("row").filter({ hasText: "v2" }).getByRole("gridcell").nth(3)).toHaveText(/^\d+$/);
    await expect(grid).toContainText("Riley");
  });

  test("Pause all and Sign out stay reachable on a phone, and the kill switch button says what it will do", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await call(page, "/settings", { kill_switch: false });
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
    await page.getByRole("button", { name: "Pause all" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Pause all" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Kill switch is on" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Turn it off (kill switch)" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Pause all" })).toHaveCount(0);
    await page.getByRole("button", { name: "Turn it off (kill switch)" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Kill switch is on" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Pause all" })).toBeVisible();
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over).toBeLessThanOrEqual(0);
  });

  test("with the kill switch on the palette offers to turn it off, and the dialog says what is really stopped", async ({ page }) => {
    await login(page); await call(page, "/settings", { kill_switch: false });
    await page.goto("/");
    await page.keyboard.press("Meta+k"); await page.keyboard.type("pause");
    await page.getByRole("option", { name: /Pause everything/ }).click();
    await expect(page.getByRole("dialog")).toContainText("every call and every message");
    await expect(page.getByRole("dialog")).not.toContainText("writing");
    await page.getByRole("dialog").getByRole("button", { name: "Pause all" }).click();
    await page.keyboard.press("Meta+k"); await page.keyboard.type("kill");
    await page.getByRole("option", { name: "Turn the kill switch off" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Kill switch is on" })).toHaveCount(0);
  });

  test("G then a number does nothing while a dialog is open", async ({ page }) => {
    await login(page); await page.goto("/");
    await page.keyboard.press("Meta+k"); await page.keyboard.type("pause");
    await page.getByRole("option", { name: /Pause everything|Turn the kill switch off/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).focus();
    await page.keyboard.press("g"); await page.keyboard.press("3");
    await expect(page).toHaveURL(/localhost:\d+\/$/);
    await page.keyboard.press("Escape");
  });

  test("the audit log opens an entry with the Open button and with Enter, in plain words", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 0);
    await page.goto("/audit");
    const grid = page.getByRole("grid", { name: "Audit log" });
    await expect(grid).toContainText("Call finished and scored");
    await expect(grid).not.toContainText("call.processed");
    await grid.getByRole("button", { name: "Open" }).first().click();
    await expect(page.getByRole("dialog")).toContainText("postcall");
    await expect(page.getByRole("dialog")).toContainText("disposition");
    await page.keyboard.press("Escape");
    await grid.focus(); await page.keyboard.press("j"); await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("a table that cannot open a row do not say Enter opens", async ({ page }) => {
    await login(page); await resetDemo(page);
    await page.goto("/metrics");
    await expect(page.locator(".rm-noopen .sx-table__footer")).toContainText("j k move");
    await expect(page.locator(".rm-noopen .sx-table__footer span").last()).toHaveCSS("font-size", "0px");
  });

  test("the call log can be searched by name or by a number written by hand, and opened with a button", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 0);
    await page.goto("/calls");
    await page.getByRole("textbox", { name: "Search by name or number" }).fill("cleo");
    const grid = page.getByRole("grid", { name: "Calls" });
    await expect(grid).toContainText("Cleo");
    await expect(grid).not.toContainText("Ben Jarrow");
    await page.getByRole("textbox", { name: "Search by name or number" }).fill("(415) 555-0102");
    await expect(grid.getByRole("row").nth(1)).toContainText("Cleo Orr");
    await expect(page.getByLabel("Outcome").locator("option", { hasText: "Call back" })).toHaveCount(1);
    await grid.getByRole("button", { name: "Open" }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("on a phone a call opens by tapping its name, with no double click and no hidden button", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page); await resetDemo(page); await runDays(page, 0);
    await page.goto("/calls");
    await page.getByRole("grid", { name: "Calls" }).getByRole("button", { name: /^[A-Z][a-z]+ [A-Z][a-z]+$/ }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.goto("/audit");
    await page.getByRole("grid", { name: "Audit log" }).getByRole("button", { name: "Call finished and scored" }).first().click();
    await expect(page.getByRole("dialog")).toContainText("Entry number");
  });

  test("a failed check is shown in plain words, never as ended_cleanly", async ({ page }) => {
    await login(page); await resetDemo(page);
    await page.goto("/qa");
    await expect(page.getByText("Ended with an outcome").first()).toBeVisible();
    await expect(page.locator("main")).not.toContainText("ended_cleanly");
    await expect(page.locator("main")).not.toContainText("Failed:");
  });

  test("follow ups name the person and the kind of message, link to the call, and cannot repeat the same text twice", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 1);
    await page.goto("/followups");
    const first = page.locator(".sx-card").filter({ hasText: "text message follow up" }).first();
    await expect(first).toContainText(/ to [A-Z][a-z]+ [A-Z][a-z]+/);
    await expect(first.getByRole("link", { name: /^Call \d+$/ })).toBeVisible();
    await expect(page.locator("main")).not.toContainText("a sms");
    const rows = await page.request.get("/api/followups");
    const pending = ((await rows.json()) as { to: string; body: string; status: string }[]).filter((f) => f.status === "pending").map((f) => `${f.to}|${f.body}`);
    expect(new Set(pending).size).toBe(pending.length); // nobody has the same text waiting twice
  });

  test("a follow up with no text cannot be approved, and a failed approvals load is an error, not an empty list", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 0);
    await page.route("**/api/followups", async (route) => {
      const real = await (await route.fetch()).json();
      await route.fulfill({ json: real.map((f: { body: string }) => ({ ...f, body: "   " })) });
    });
    await page.goto("/followups");
    await expect(page.getByText(/no text, so there is nothing to approve/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve" }).first()).toHaveAttribute("aria-disabled", "true");
    await page.unroute("**/api/followups");
    await page.route("**/api/approvals", (route) => route.fulfill({ status: 500, json: { error: { message: "Test failure" } } }));
    await page.goto("/followups");
    await expect(page.getByText("Could not load approvals")).toBeVisible();
    await expect(page.getByText("Approvals (0)")).toHaveCount(0);
  });

  test("failed loads show an error with a retry, not an empty list or a spinner forever", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 0);
    const fail = (re: RegExp) => page.route(re, (route) => route.fulfill({ status: 500, json: { error: { message: "Test failure" } } }));
    await fail(/\/api\/suppressions/); await page.goto("/numbers");
    await expect(page.getByText("Could not load the do not call list")).toBeVisible();
    await page.unroute(/\/api\/suppressions/);
    await fail(/\/api\/metrics\/versions/); await page.goto("/metrics");
    await expect(page.getByText("Could not load the prompt versions")).toBeVisible();
    await page.unroute(/\/api\/metrics\/versions/);
    await fail(/\/api\/calls\/\d+$/); await page.goto("/live");
    await expect(page.getByText("Could not load this call")).toBeVisible();
    await page.unroute(/\/api\/calls\/\d+$/);
    await fail(/\/api\/settings/); await page.goto("/");
    await expect(page.getByText(/Mode: not known yet/)).toBeVisible();
    await expect(page.locator("main")).not.toContainText("Mode: Live");
  });

  test("do not call entries say where they came from in plain words", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 1);
    await page.goto("/numbers");
    const list = page.getByRole("list", { name: "Do not call list" });
    await expect(list).toContainText("Starting list");
    await expect(list).toContainText(/Call \d+/);
    await expect(list).not.toContainText(/^seed$/m);
  });

  test("integrations say each thing once, name the offline stand in, and show what a test said", async ({ page }) => {
    await login(page);
    await page.goto("/integrations");
    await expect(page.getByTestId("tier-legend")).toContainText("Tier A");
    await expect(page.locator("main")).not.toContainText("Recipe prompt only. Recipe prompt");
    await expect(page.locator("main")).not.toContainText("Built and tested against a mock. Tested against a mock");
    await expect(page.getByText("Using the offline stand in (seed).").first()).toBeVisible();
    await page.getByRole("button", { name: "Test connection" }).first().click();
    await expect(page.getByText("No call is placed.").first()).toBeVisible();
  });

  test("signing in lands on the page that was asked for, and ignores an address on another site", async ({ page }) => {
    await page.goto("/calls");
    await expect(page).toHaveURL(/\/login\?next=%2Fcalls/);
    await page.getByLabel("Email").fill("owner@example.test");
    await page.getByLabel("Password").fill("demo-password-1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Call log" })).toBeVisible();
    await page.context().clearCookies();
    await page.goto("/login?next=https://elsewhere.example/steal");
    await page.getByLabel("Email").fill("owner@example.test");
    await page.getByLabel("Password").fill("demo-password-1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    await expect(page).toHaveURL(/localhost:\d+\/$/);
  });

  test("changing the share of a split test is saved, and shows after a reload", async ({ page }) => {
    await login(page); await resetDemo(page);
    await page.goto("/agents");
    await page.getByLabel("Candidate").selectOption({ label: "Version 1" });
    await expect(page.getByText("Split test updated.")).toBeVisible();
    await page.getByLabel("Share of calls").selectOption("30%");
    await expect(page.getByText("Split test updated.").first()).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Share of calls")).toHaveValue("0.3");
    await expect(page.getByText("split test 30%")).toBeVisible();
  });

  test("a CSV file dropped on the import box is read, and the paste box and preview follow", async ({ page }) => {
    await login(page); await resetDemo(page);
    await page.goto("/campaigns");
    await page.getByRole("button", { name: "Import" }).first().click();
    const zone = page.locator(".rm-file");
    const dt = await page.evaluateHandle(() => { const d = new DataTransfer(); d.items.add(new File(["first_name,phone,timezone\nDrop,+14155550888,America/New_York\n"], "dropped.csv", { type: "text/csv" })); return d; });
    await zone.dispatchEvent("dragover", { dataTransfer: dt });
    await expect(zone).toHaveAttribute("data-over", "true");
    await zone.dispatchEvent("drop", { dataTransfer: dt });
    await expect(page.getByText("dropped.csv")).toBeVisible();
    await expect(page.getByLabel("Preview of the first rows")).toContainText("Drop");
    await expect(page.getByLabel("Or paste CSV text")).toHaveValue(/Drop,\+14155550888/);
  });

  test("no console errors or failed requests while walking every page as the owner", async ({ page }) => {
    const errors = watch(page);
    await login(page); await resetDemo(page); await runDays(page, 1);
    for (const p of ["/", "/live", "/calls", "/campaigns", "/agents", "/numbers", "/qa", "/followups", "/metrics", "/integrations", "/audit"]) {
      await page.goto(p); await page.waitForLoadState("networkidle");
    }
    expect(errors.filter((e) => !/ERR_ABORTED|events\/stream/.test(e))).toEqual([]);
  });
});
