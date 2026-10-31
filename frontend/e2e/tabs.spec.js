import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks.js";

// Regression test for the tab-state-persistence fix: tabs used to fully
// unmount on switch, resetting the Recommend chat log and any in-progress
// form state the moment you navigated away and back.
test("the Recommend chat survives switching to another tab and back", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Recommend" }).click();

  await page.getByLabel("Describe the project in free text").fill("headless pc for local AI");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("headless pc for local AI")).toBeVisible();
  await expect(page.getByText("Build 1")).toBeVisible();

  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(page.getByText("Build 1")).not.toBeVisible();

  await page.getByRole("button", { name: "Recommend" }).click();
  await expect(page.getByText("headless pc for local AI")).toBeVisible();
  await expect(page.getByText("Build 1")).toBeVisible();
});

test("an in-progress manual-add form in Inventory survives switching tabs", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  await page.getByLabel("Name", { exact: true }).fill("My custom CPU");

  await page.getByRole("button", { name: "Backup" }).click();
  await expect(page.getByLabel("Name", { exact: true })).not.toBeVisible();

  await page.getByRole("button", { name: "Inventory" }).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("My custom CPU");
});
