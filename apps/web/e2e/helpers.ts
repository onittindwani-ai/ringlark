import { expect, type Page } from "@playwright/test";

export const PAGES = ["/", "/live", "/calls", "/campaigns", "/agents", "/numbers", "/qa", "/followups", "/metrics", "/integrations", "/audit"];

export function watch(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("response", (r) => r.status() >= 400 && errors.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`));
  return errors;
}

export async function login(page: Page, email = "owner@example.test") {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

export const call = (page: Page, path: string, json?: unknown) => page.request.post(`/api${path}`, { headers: { "x-ringlark": "1", "content-type": "application/json" }, data: json ?? {} });

export async function resetDemo(page: Page) {
  const r = await call(page, "/demo/reset");
  expect(r.ok()).toBeTruthy();
}

/** Place the demo calls, move a day, and run again so a second round happens. */
export async function runDays(page: Page, days = 1) {
  await call(page, "/demo/tick");
  for (let i = 0; i < days; i++) {
    await call(page, "/demo/advance", { hours: 24 });
    await call(page, "/demo/tick");
  }
}
