import { expect, test } from "@playwright/test";
import { activePane, mockApi } from "./mocks.js";

test("lets you pick local or Azure as the backup destination", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Backup" }).click();
  const pane = activePane(page);

  await expect(pane.getByRole("button", { name: "Local" })).toBeVisible();
  await expect(pane.getByRole("button", { name: "Azure (cloud)" })).toBeVisible();
  await expect(pane.getByText("Active backend:")).toContainText("local");

  const listRequest = page.waitForRequest((req) => req.url().includes("backend=azure"));
  await pane.getByRole("button", { name: "Azure (cloud)" }).click();
  await listRequest;

  const createRequest = page.waitForRequest(
    (req) => req.url().endsWith("/api/backup") && req.method() === "POST",
  );
  await pane.getByRole("button", { name: "Create backup now" }).click();
  const request = await createRequest;
  expect(request.postDataJSON()).toEqual({ backend: "azure" });
});

test("hides the Azure option when it isn't configured on the server", async ({ page }) => {
  await mockApi(page, {
    backups: { backup_backend: "local", destination: "/app/backups", available_backends: ["local"], backups: [] },
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Backup" }).click();
  const pane = activePane(page);

  await expect(pane.getByRole("button", { name: "Local" })).toBeVisible();
  await expect(pane.getByRole("button", { name: "Azure (cloud)" })).not.toBeVisible();
  await expect(pane.getByText(/isn't configured on the server/)).toBeVisible();
});
