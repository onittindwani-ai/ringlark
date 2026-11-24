import { expect, test, type Page } from "@playwright/test";

function watch(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

test("sign in, load demo data, visit every page with no console errors", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.request.post("/api/demo/reset", { headers: { "x-ringlark": "1" } });
  for (const path of ["/", "/live", "/calls", "/campaigns", "/agents", "/numbers", "/qa", "/followups", "/metrics", "/integrations", "/audit"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h1").first()).toBeVisible();
  }
  expect(errors.filter((e) => !/favicon/.test(e)), errors.join("\n")).toEqual([]);
});
