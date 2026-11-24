import { expect, test, type Page } from "@playwright/test";
import { join } from "node:path";
import { call, login, resetDemo, runDays, watch } from "./helpers";

const fx = (n: string) => join(__dirname, "fixtures", n);
const importDialog = async (page: Page) => { await page.goto("/campaigns"); await page.getByRole("button", { name: "Import" }).first().click(); };

test.describe("round 5 fixes", () => {
  test("typing reset in the palette puts Reset the demo data first, and G then a number goes to that page", async ({ page }) => {
    await login(page);
    await page.waitForLoadState("networkidle");
    await page.keyboard.press("Meta+k");
    await page.keyboard.type("reset");
    await expect(page.getByRole("option").first()).toContainText("Reset the demo data");
    await page.keyboard.press("Escape");
    await page.keyboard.press("g");
    await page.keyboard.press("3");
    await expect(page).toHaveURL(/\/calls$/);
  });

  test("a refused file empties the paste box and keeps Import off, so an earlier file is never sent again", async ({ page }) => {
    await login(page); await resetDemo(page);
    await importDialog(page);
    const imp = page.getByRole("dialog").getByRole("button", { name: "Import", exact: true });
    await expect(imp).toHaveAttribute("aria-disabled", "true"); // nothing chosen yet: no sample person is sent
    await page.getByLabel("Choose a CSV file").setInputFiles(fx("upload-people.csv"));
    await expect(imp).not.toHaveAttribute("aria-disabled", "true");
    await page.getByLabel("Choose a CSV file").setInputFiles(fx("empty.csv"));
    await expect(page.getByText(/no data rows/)).toBeVisible();
    await expect(page.getByLabel("Or paste CSV text")).toHaveValue("");
    await expect(imp).toHaveAttribute("aria-disabled", "true");
    await page.getByLabel("Choose a CSV file").setInputFiles(fx("no-phone.csv"));
    await expect(imp).toHaveAttribute("aria-disabled", "true"); // no phone column
  });

  test("a semicolon file and a Latin 1 file import correctly, and the dialog starts empty the next time", async ({ page }) => {
    await login(page); await resetDemo(page);
    await importDialog(page);
    await page.getByLabel("Choose a CSV file").setInputFiles(fx("semicolon.csv"));
    await expect(page.getByText(/1 row, 4 columns/)).toBeVisible();
    await page.getByLabel("Choose a CSV file").setInputFiles(fx("latin1.csv"));
    await expect(page.getByLabel("Preview of the first rows")).toContainText("José");
    await page.getByRole("dialog").getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByText(/Imported 1/)).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Import", exact: true }).first().click();
    await expect(page.getByLabel("Or paste CSV text")).toHaveValue("");
  });

  test("more than 5000 people is refused on screen before anything is sent", async ({ page }) => {
    await login(page); await resetDemo(page);
    await importDialog(page);
    const rows = Array.from({ length: 5001 }, (_, i) => `+1415${String(i).padStart(7, "0")}`).join("\n");
    await page.getByLabel("Or paste CSV text").fill(`phone\n${rows}`);
    await expect(page.getByRole("dialog").getByRole("button", { name: "Import", exact: true })).toHaveAttribute("aria-disabled", "true");
  });

  test("a viewer sees the write buttons switched off instead of getting a refusal", async ({ page }) => {
    const errors = watch(page);
    await login(page, "viewer@example.test"); await page.context().clearCookies();
    await login(page, "owner@example.test"); await resetDemo(page); await runDays(page, 1);
    await page.context().clearCookies();
    await login(page, "viewer@example.test");
    for (const [path, name] of [["/campaigns", "New campaign"], ["/followups", "Approve"], ["/qa", "Mark as read"], ["/live", "Take over"]] as const) {
      await page.goto(path);
      await expect(page.getByRole("button", { name }).first()).toHaveAttribute("aria-disabled", "true");
    }
    await expect(page.getByRole("button", { name: "Run now" })).toHaveAttribute("aria-disabled", "true");
    await page.goto("/integrations");
    await expect(page.getByRole("button", { name: "Test connection" })).toHaveCount(0);
    expect(errors.filter((e) => /40[13]/.test(e))).toEqual([]);
  });

  test("Take over on a replayed demo call says it was a practice run", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 0);
    await page.goto("/live");
    await page.getByRole("button", { name: "Take over" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Take over" }).click();
    await expect(page.getByText(/Practice run/)).toBeVisible();
  });

  test("a call nobody answered has no player, and the QA link opens that exact call", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 1);
    await page.goto("/calls");
    await page.getByLabel("Outcome").selectOption("no_answer");
    await page.getByRole("button", { name: /Length/ }).click(); // shortest first: a call that never connected
    await page.getByRole("grid", { name: "Calls" }).focus();
    await page.keyboard.press("j"); await page.keyboard.press("Enter");
    await expect(page.getByText(/No one spoke on this call/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Play" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await page.goto("/qa");
    const link = page.getByRole("link", { name: "Open it in the call log" }).first();
    const href = await link.getAttribute("href");
    expect(href).toMatch(/\/calls\?open=\d+/);
    await link.click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("right after saving a prompt the compare view already shows the change, and an approved follow up says what it waits for", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 1);
    await page.goto("/agents");
    const box = page.getByLabel(/^Prompt \(version/);
    await box.fill((await box.inputValue()) + "\nAlways say the practice name first.");
    await page.getByRole("button", { name: /Save as a new version/ }).click();
    await expect(page.getByText(/Saved as version/)).toBeVisible();
    await expect(page.getByText("Pick two different versions.")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Prompt differences" })).toContainText("practice name first");
    await page.goto("/followups");
    await page.getByRole("button", { name: "Approve" }).first().click();
    await page.getByRole("tab", { name: "All follow ups" }).click();
    await expect(page.getByText("approved, sends on the next run").first()).toBeVisible();
  });

  test("the chart axis shows short dates, and the kill switch makes Run now say nothing ran", async ({ page }) => {
    await login(page); await resetDemo(page); await runDays(page, 1);
    await page.goto("/");
    await expect(page.locator("svg text").filter({ hasText: /^[A-Z][a-z]{2} \d{1,2}$/ }).first()).toBeVisible();
    await call(page, "/settings", { kill_switch: true });
    await page.reload();
    await page.waitForLoadState("networkidle");
    await page.keyboard.press("Meta+k");
    await page.getByRole("option", { name: /Run every job now/ }).click();
    await expect(page.getByText(/Nothing ran: the kill switch is on/)).toBeVisible();
    await call(page, "/settings", { kill_switch: false });
  });
});
