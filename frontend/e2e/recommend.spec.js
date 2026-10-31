import { expect, test } from "@playwright/test";
import { activePane, mockApi } from "./mocks.js";

test("sends a prompt and shows the assistant reply, builds, and score guide", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Recommend" }).click();

  // <summary> doesn't expose a "button" role in Chromium's accessibility
  // tree, so target it by its text instead.
  await activePane(page).getByText("What does the score mean?").click();
  await expect(page.getByText(/Every build starts with a score of 100/)).toBeVisible();

  const textarea = page.getByLabel("Describe the project in free text");
  await textarea.fill("headless pc for local AI");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(
    page.getByText("Here is a build from your inventory that fits what you asked for."),
  ).toBeVisible();
  await expect(page.getByText("Build 1")).toBeVisible();
  await expect(page.getByText("Meets the stated requirements.")).toBeVisible();
  await expect(page.getByText("Interpretation: ok")).toBeVisible();
});

test("a build can be saved from the chat", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Recommend" }).click();

  await page.getByLabel("Describe the project in free text").fill("headless pc for local AI");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Build 1")).toBeVisible();

  await page.getByRole("button", { name: "Save build" }).click();

  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
});
