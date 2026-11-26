import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { PAGES, call, login, resetDemo, watch } from "./helpers";

const OUT = join(__dirname, "..", "..", "..", "docs", "screenshots");
mkdirSync(OUT, { recursive: true });
const sizes = [{ tag: "desktop", width: 1440, height: 900 }, { tag: "mobile", width: 390, height: 844 }] as const;

for (const s of sizes) {
  test.describe(s.tag, () => {
    test.use({ viewport: { width: s.width, height: s.height } });

    test("screenshots of every state", async ({ page }) => {
      const errors = watch(page);
      const shot = (name: string) => page.screenshot({ path: join(OUT, `${s.tag}-${name}.png`) });
      await login(page);
      await resetDemo(page);

      await page.goto("/calls");
      await page.getByLabel("Search by name or number").fill("9999999");
      await expect(page.getByText("No calls match")).toBeVisible();
      await shot("06-empty-calls");

      await page.goto("/");
      await page.getByRole("button", { name: "Run now" }).click();
      await page.waitForTimeout(250);
      await shot("04-button-processing");
      await expect(page.getByText(/Ran every job/)).toBeVisible();
      await page.waitForTimeout(600);
      await shot("05-toast");
      await page.goto("/");
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1300);
      await shot("01-overview-default");
      await page.getByText("Held back by the rules").scrollIntoViewIfNeeded();
      await page.waitForTimeout(600);
      await shot("03-warning-held-back");

      await page.goto("/calls");
      await page.getByLabel("Outcome").selectOption("booked");
      await page.getByRole("grid", { name: "Calls" }).focus();
      await page.keyboard.press("j");
      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.getByLabel("Call position").fill("12000");
      await page.waitForTimeout(1300);
      await shot("02-detail-call-scrubber");
      await page.keyboard.press("Escape");

      await page.goto("/live");
      await page.getByRole("radio", { name: "4x" }).click();
      await page.getByRole("button", { name: "Play" }).click();
      await page.waitForTimeout(4200);
      await shot("09-live-console");

      for (const [path, name] of [["/campaigns", "10-campaigns"], ["/agents", "11-agents"], ["/numbers", "12-numbers"], ["/qa", "13-qa"], ["/followups", "14-followups"], ["/metrics", "15-metrics"], ["/integrations", "16-integrations"], ["/audit", "17-audit"]] as const) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(800);
        await shot(name);
      }
      await page.goto("/agents");
      await page.getByRole("tab", { name: "Simulator and persona suite" }).click();
      await page.getByRole("button", { name: /Run the suite on version/ }).click();
      await expect(page.getByText(/of 14 passed/)).toBeVisible();
      await page.waitForTimeout(700);
      await shot("18-persona-suite");

      await page.route("**/api/overview", (r) => r.abort());
      await page.goto("/");
      await expect(page.getByText("Could not load the overview")).toBeVisible();
      await shot("07-error-overview");
      await page.unroute("**/api/overview");

      await page.goto("/");
      await page.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
      await page.waitForTimeout(1300);
      await shot("08-dark-overview");
      await page.goto("/live");
      await page.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
      await page.waitForTimeout(700);
      await shot("19-dark-live");
      expect(errors.filter((e) => !/favicon|ERR_FAILED|net::|Failed to load resource/.test(e)), errors.join("\n")).toEqual([]);
    });
  });
}

test.describe("accessibility and behaviour", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await resetDemo(page);
    await call(page, "/demo/tick");
  });

  test("axe finds no serious or critical problems on any page, light and dark", async ({ page }) => {
    for (const theme of ["light", "dark"]) {
      for (const path of PAGES) {
        await page.goto(path);
        await page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(1000);
        const res = await new AxeBuilder({ page }).analyze();
        const bad = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(bad.map((v) => `${theme} ${path}: ${v.id} ${v.help} (${v.nodes.length})`), `${theme} ${path}`).toEqual([]);
      }
    }
  });

  test("keyboard only: command palette, table keys, dialogs close with escape", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.type("Go to Call log");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/calls/);
    const grid = page.getByRole("grid", { name: "Calls" });
    await expect(grid).toBeVisible();
    await grid.focus();
    await page.keyboard.press("j");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.goto("/live");
    await expect(page.locator("main")).toBeVisible();
    for (let i = 0; i < 4; i++) await page.keyboard.press("Tab"); // a few presses always land on something; many presses leave the page on a short screen
    expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
  });

  test("reduced motion removes page and chart animation", async ({ browser }) => {
    const ctx = await browser.newContext({ reducedMotion: "reduce", baseURL: `http://localhost:${process.env.WEB_PORT ?? "3000"}` });
    const page = await ctx.newPage();
    await login(page);
    await page.goto("/");
    await page.waitForTimeout(300);
    const names = await page.evaluate(() => [".rm-page", ".rm-funnel__fill"].map((s) => { const el = document.querySelector(s); return el ? getComputedStyle(el).animationName : "missing"; }));
    expect(names).toEqual(["none", "none"]);
    await ctx.close();
  });

  test("a call table with 5,000 rows stays light and the page does not shift while loading", async ({ page }) => {
    const r = await call(page, "/demo/stress-calls", { n: 5000 });
    expect(r.ok()).toBeTruthy();
    await page.addInitScript(() => {
      (window as unknown as { __cls: number }).__cls = 0;
      new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { hadRecentInput: boolean; value: number }[]) if (!e.hadRecentInput) (window as unknown as { __cls: number }).__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
    });
    await page.goto("/calls");
    const grid = page.getByRole("grid", { name: "Calls" });
    await expect(grid).toBeVisible();
    await expect(page.locator('[role="row"]').nth(3)).toBeVisible();
    expect(await page.locator('[role="row"]').count()).toBeLessThan(120);
    const t0 = Date.now();
    await grid.focus();
    for (let i = 0; i < 30; i++) await page.keyboard.press("j");
    expect(Date.now() - t0).toBeLessThan(4000);
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    expect(await page.evaluate(() => (window as unknown as { __cls: number }).__cls)).toBeLessThan(0.1);
    await resetDemo(page);
  });
});
