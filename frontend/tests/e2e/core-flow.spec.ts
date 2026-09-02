import { expect, test } from "@playwright/test";

const taskId = process.env.E2E_TASK_ID;

test.describe("真实课堂证据工作台", () => {
  test.skip(!taskId, "设置 E2E_TASK_ID 后才会读取已完成的本地真实任务；CI 不伪造媒体结果。");

  test("恢复安全会话并展示可定位的课件、逐字稿和视频证据", async ({ page }) => {
    await page.goto(`/tasks/${taskId}`);
    const workbench = page.locator(".evidence-workbench.real");
    await expect(workbench).toBeVisible();
    await expect(page.locator(".courseware-evidence-panel")).toBeVisible();
    await expect(page.locator(".transcript-timeline")).toBeVisible();
    await expect(page.locator(".real-conclusion-card").first()).toBeVisible();

    const layout = await page.evaluate(() => {
      const media = document.querySelector(".evidence-media-column")?.getBoundingClientRect();
      const review = document.querySelector(".evidence-review-column")?.getBoundingClientRect();
      if (!media || !review) return null;
      return {
        viewportWidth: window.innerWidth,
        pageWidth: document.documentElement.scrollWidth,
        overlaps: Math.min(media.right, review.right) > Math.max(media.left, review.left),
      };
    });
    expect(layout).not.toBeNull();
    expect(layout?.pageWidth).toBeLessThanOrEqual(layout?.viewportWidth ?? 0);
    if ((layout?.viewportWidth ?? 0) >= 901) expect(layout?.overlaps).toBeFalsy();

    const coursewareReference = page.locator(".real-evidence-references button", { hasText: "课件" }).first();
    await expect(coursewareReference).toBeVisible();
    await coursewareReference.click();
    await expect(page.locator("#courseware-evidence-panel")).toBeInViewport();
    await expect(page.locator("#courseware-evidence-panel blockquote")).not.toBeEmpty();
  });
});
