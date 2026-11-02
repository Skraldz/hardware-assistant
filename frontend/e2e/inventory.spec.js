import { expect, test } from "@playwright/test";
import { SAMPLE_COMPONENTS, mockApi } from "./mocks.js";

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

test("shows each component's release year in its own column", async ({ page }) => {
  await mockApi(page, {
    components: [
      { ...SAMPLE_COMPONENTS[0], release_year: 2008 },
      { ...SAMPLE_COMPONENTS[1], release_year: 2024 },
    ],
  });
  await page.goto("/");

  const rows = page.locator("tbody tr");
  await expect(rows.filter({ hasText: "AMD Ryzen 5 3600" })).toContainText("2008");
  await expect(rows.filter({ hasText: "NVIDIA GeForce RTX 2060" })).toContainText("2024");
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

test("extracted release year is prefilled and editable before saving", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  await page.getByLabel("Component name").fill("RTX 2060 SUPER");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByText("NVIDIA GeForce RTX 2060 SUPER Specs", { exact: false }).click();
  await expect(page.getByText(/Extracted specs for/)).toBeVisible();

  // The manual-add section below also has a "Release year" field -- this
  // one (inside the extracted-specs confirm panel) comes first in the DOM.
  const releaseYearField = page.getByLabel("Release year").first();
  await expect(releaseYearField).toHaveValue("2019");

  await releaseYearField.fill("2020");

  const saveRequest = page.waitForRequest(
    (req) => req.url().endsWith("/api/components") && req.method() === "POST",
  );
  await page.getByRole("button", { name: "Confirm and save" }).click();
  const request = await saveRequest;
  expect(request.postDataJSON().release_year).toBe(2020);
});

test("clearing the inventory requires confirmation and reports the result", async ({ page }) => {
  await mockApi(page);
  // Two dialogs fire here: a confirm() asking to proceed, then an alert()
  // reporting the result once the request resolves -- wait for both before
  // the test ends, or the second one's accept() races test teardown.
  const dialogMessages = [];
  page.on("dialog", async (dialog) => {
    dialogMessages.push(dialog.message());
    await dialog.accept();
  });
  await page.goto("/");

  const clearRequest = page.waitForRequest(
    (req) => req.url().endsWith("/api/components/clear") && req.method() === "POST",
  );
  await page.getByRole("button", { name: "Clear inventory" }).click();
  const request = await clearRequest;
  expect(request.postDataJSON()).toEqual({ confirm: true });

  await expect.poll(() => dialogMessages.length).toBeGreaterThanOrEqual(2);
  expect(dialogMessages[1]).toContain("Inventory cleared");
});

test("declining the clear-inventory confirmation sends no request", async ({ page }) => {
  await mockApi(page);
  page.on("dialog", (dialog) => dialog.dismiss());
  await page.goto("/");

  let cleared = false;
  await page.route("**/api/components/clear", (route) => {
    cleared = true;
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await page.getByRole("button", { name: "Clear inventory" }).click();
  await expect(page.getByText("Inventory (2)")).toBeVisible();
  expect(cleared).toBe(false);
});

test("reseeding the inventory adds on top without clearing it first", async ({ page }) => {
  await mockApi(page);
  const dialogMessages = [];
  page.on("dialog", async (dialog) => {
    dialogMessages.push(dialog.message());
    await dialog.accept();
  });
  await page.goto("/");

  const reseedRequest = page.waitForRequest(
    (req) => req.url().endsWith("/api/components/reseed") && req.method() === "POST",
  );
  await page.getByRole("button", { name: "Populate with demo data" }).click();
  const request = await reseedRequest;
  expect(request.postDataJSON()).toEqual({ confirm: true });

  await expect.poll(() => dialogMessages.length).toBeGreaterThanOrEqual(2);
  expect(dialogMessages[1]).toContain("Demo data added");
});

// Regression test: the name field used to stay disabled while a result was
// under review, as a (now-redundant) guard against a name-drift bug that's
// actually prevented by handleConfirmSave freezing its own confirmName
// state -- the field no longer needs to lock at all.
test("the component name field stays editable after a result is extracted", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  const nameField = page.getByLabel("Component name");
  await nameField.fill("RTX 2060 SUPER");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByText("NVIDIA GeForce RTX 2060 SUPER Specs", { exact: false }).click();
  await expect(page.getByText(/Extracted specs for/)).toBeVisible();

  await expect(nameField).toBeEnabled();
  await nameField.fill("A completely different part");
  await expect(nameField).toHaveValue("A completely different part");
});
