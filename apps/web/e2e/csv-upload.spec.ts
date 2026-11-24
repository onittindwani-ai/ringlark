import { expect, test } from "@playwright/test";
import { join } from "node:path";
import { login, resetDemo } from "./helpers";

const FILE = join(__dirname, "fixtures", "upload-people.csv");

test("choose a CSV file, see the preview, import it, and the new people appear with the rules applied", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/campaigns");
  await page.getByRole("button", { name: "Import" }).first().click();
  await page.getByLabel("Choose a CSV file").setInputFiles(FILE);
  await expect(page.getByText(/3 rows, 4 columns/)).toBeVisible();
  await expect(page.getByLabel("Preview of the first rows")).toBeVisible();
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByText(/Imported 3/)).toBeVisible();
  const toggle = page.getByRole("button", { name: "Show people" }).first();
  if ((await toggle.getAttribute("aria-pressed")) !== "true") await toggle.click();
  const person = page.getByRole("button", { name: "Person", exact: true });
  await person.click();
  await person.click();
  await expect(page.getByText("Zora Quill")).toBeVisible();
  await expect(page.getByText("Not a full phone number")).toBeVisible();
});
