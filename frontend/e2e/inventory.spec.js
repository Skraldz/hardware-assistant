import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks.js";

test("lists seeded components and filters by category", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  await expect(page.getByText("Inventory (2)")).toBeVisible();
  await expect(page.getByText("AMD Ryzen 5 3600")).toBeVisible();
  await expect(page.getByText("NVIDIA GeForce RTX 2060 6GB")).toBeVisible();

  await page.getByRole("button", { name: "gpu", exact: true }).click();

  await expect(page.getByText("NVIDIA GeForce RTX 2060 6GB")).toBeVisible();
  await expect(page.getByText("AMD Ryzen 5 3600")).not.toBeVisible();
});

test("sorting by name toggles order", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  const nameHeader = page.getByRole("button", { name: /^Name/ });
  await nameHeader.click();

  const rows = page.locator("tbody tr");
  await expect(rows.first()).toContainText("AMD Ryzen 5 3600");

  await nameHeader.click();
  await expect(rows.first()).toContainText("NVIDIA GeForce RTX 2060 6GB");
});

test("manual-add JSON template changes with the selected category", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  const specsBox = page.getByLabel("Specs (JSON — fields you don't know can be left out)");
  await expect(specsBox).toHaveValue(/"category": "cpu"/);
  await expect(specsBox).not.toHaveValue(/vram_gb/);

  // Chromium concatenates a <select>'s accessible name with all of its
  // option text, so getByLabel can't reliably target it here -- the
  // "cooler" option is unique to this select (vs. Condition/Language).
  const categorySelect = page.locator("select").filter({ has: page.locator('option[value="cooler"]') });
  await categorySelect.selectOption("gpu");

  await expect(specsBox).toHaveValue(/"category": "gpu"/);
  await expect(specsBox).toHaveValue(/vram_gb/);
});

test("open-in-new-tab link on a search result does not select it as the match", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  await page.getByLabel("Component name").fill("RTX 2060 SUPER");
  await page.getByRole("button", { name: "Search" }).click();

  const openLink = page.getByRole("link", { name: /Open in new tab/i });
  await expect(openLink).toHaveAttribute("target", "_blank");
  await expect(openLink).toHaveAttribute(
    "href",
    "https://example.com/rtx-2060-super",
  );
  // Clicking it must not trigger the candidate-pick extract flow.
  await expect(page.getByText(/Extracted specs for/)).not.toBeVisible();
});
