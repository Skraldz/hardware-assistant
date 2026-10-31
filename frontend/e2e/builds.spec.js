import { expect, test } from "@playwright/test";
import { activePane, mockApi } from "./mocks.js";

test("lists a saved build and can mark it as built", async ({ page }) => {
  await mockApi(page);
  // "Mark as built" is behind a native confirm() -- auto-accept it, the way
  // a real user clicking "OK" would (Playwright can drive this directly,
  // unlike manual browser automation, which must avoid native dialogs).
  page.on("dialog", (dialog) => dialog.accept());

  await page.goto("/");
  await page.getByRole("button", { name: "Builds" }).click();
  const pane = activePane(page);

  await expect(pane.getByText("AMD Ryzen 5 3600")).toBeVisible();
  await expect(pane.getByText("Not built yet")).toBeVisible();
  await expect(pane.getByText("play Baldur's Gate 3 at max resolution and 60 FPS")).toBeVisible();

  const completeRequest = page.waitForRequest(
    (req) => req.url().includes("/complete") && req.method() === "POST",
  );
  await pane.getByRole("button", { name: "Mark as built" }).click();
  await completeRequest;

  await expect(pane.getByText(/error/i)).not.toBeVisible();
});

test("shows an empty state with no saved builds", async ({ page }) => {
  await mockApi(page, { builds: [] });
  await page.goto("/");
  await page.getByRole("button", { name: "Builds" }).click();

  await expect(activePane(page).getByText("No saved builds yet.", { exact: false })).toBeVisible();
});
