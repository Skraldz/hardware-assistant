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

test("a build can be saved from the chat, with the original ask as its purpose", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Recommend" }).click();

  await page
    .getByLabel("Describe the project in free text")
    .fill("play Baldur's Gate 3 at max resolution and 60 FPS");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Build 1")).toBeVisible();

  const saveRequest = page.waitForRequest(
    (req) => req.url().endsWith("/api/builds") && req.method() === "POST",
  );
  await page.getByRole("button", { name: "Save build" }).click();
  const request = await saveRequest;

  expect(request.postDataJSON().purpose).toBe("play Baldur's Gate 3 at max resolution and 60 FPS");
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
});

// Regression test: saveState was keyed by "<messageIndex>-<buildIndex>",
// and "New conversation" reset the message list but not that save state --
// a new conversation's first build reused the same key as the previous
// conversation's first build, so it incorrectly showed as already saved.
test("a new conversation's builds are not pre-marked as saved", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Recommend" }).click();

  await page.getByLabel("Describe the project in free text").fill("headless pc for local AI");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Build 1")).toBeVisible();
  await page.getByRole("button", { name: "Save build" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();

  await page.getByRole("button", { name: "New conversation" }).click();
  await page.getByLabel("Describe the project in free text").fill("a different build request");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Build 1")).toBeVisible();

  await expect(page.getByRole("button", { name: "Save build" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Saved" })).not.toBeVisible();
});
