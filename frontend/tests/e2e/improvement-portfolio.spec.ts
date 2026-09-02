import { expect, test, type Page } from "@playwright/test";

const cycleId = process.env.E2E_CYCLE_ID;

async function expectResponsivePage(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
}

test.describe("M2 改进循环与 M3 课程总览", () => {
  test.skip(
    !process.env.E2E_BASE_URL,
    "设置 E2E_BASE_URL 后才连接真实运行服务；CI 只校验规范，不伪造后端会话。",
  );

  test("教师可以进入改进循环并看到真实与合成证据边界", async ({ page }) => {
    await page.goto("/improvements");
    await expect(page.getByRole("heading", { name: "把复盘建议，变成下一轮可验证的行动" })).toBeVisible();
    await expect(page.getByText("合成轮次只验证系统机制，永不进入真实教学成效汇总。" )).toBeVisible();
    await expect(page.getByText("正在载入…")).toHaveCount(0);
    await expectResponsivePage(page);
  });

  test("教师可以进入课程总览且课堂链接只使用真实任务 ID", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.getByRole("heading", { name: "多门课程，在同一条证据边界内被看见" })).toBeVisible();
    await expect(page.getByText("正在载入课程总览…")).toHaveCount(0);
    await expect(page.getByText(/不汇总合成验证轮次/)).toBeVisible();
    const taskLinks = page.locator('.portfolio-classroom a[href^="/tasks/"]');
    for (let index = 0; index < await taskLinks.count(); index += 1) {
      await expect(taskLinks.nth(index)).toHaveAttribute("href", /^\/tasks\/[0-9a-f-]{36}$/);
    }
    await expectResponsivePage(page);
  });

  test("改进循环工作台保持教师确认门禁", async ({ page }) => {
    test.skip(!cycleId, "设置 E2E_CYCLE_ID 后验证本地改进循环；CI 不伪造教学改进结果。");
    await page.goto(`/improvements/${cycleId}`);
    await expect(page.getByText("系统不会因为关联了课堂就假定教学已经改进。")).toBeVisible();
    await expectResponsivePage(page);
  });
});
