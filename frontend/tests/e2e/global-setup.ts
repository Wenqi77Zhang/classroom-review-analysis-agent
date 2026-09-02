import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { request } from "@playwright/test";

export const E2E_AUTH_STATE_PATH = resolve(
  process.cwd(),
  "test-results/e2e-auth-state.json",
);

export default async function globalSetup() {
  const baseURL = process.env.E2E_BASE_URL;
  if (!baseURL) {
    throw new Error("真实 E2E 需要 E2E_BASE_URL；不会在没有运行服务时伪造结果。");
  }

  const teacherEmail = process.env.E2E_TEACHER_EMAIL;
  const teacherPassword = process.env.E2E_TEACHER_PASSWORD;
  if (Boolean(teacherEmail) !== Boolean(teacherPassword)) {
    throw new Error("E2E_TEACHER_EMAIL 与 E2E_TEACHER_PASSWORD 必须同时提供。");
  }

  const api = await request.newContext({ baseURL });
  try {
    const response = teacherEmail
      ? await api.post("/api/session/login", {
          data: { email: teacherEmail, password: teacherPassword },
        })
      : await api.post("/api/session/demo");
    if (!response.ok()) {
      throw new Error(
        `E2E 会话初始化失败（HTTP ${response.status()}）；请提供正式教师凭据，或在本地明确启用演示账号。`,
      );
    }
    mkdirSync(dirname(E2E_AUTH_STATE_PATH), { recursive: true });
    await api.storageState({ path: E2E_AUTH_STATE_PATH });
  } finally {
    await api.dispose();
  }
}
