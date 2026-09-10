import assert from "node:assert/strict";
import test from "node:test";
import { safeNextPath, redirectToLogin } from "../src/lib/session-path.ts";

test("登录返回路径拒绝跨域、反斜线和控制字符绕过", () => {
  for (const path of [null, "https://evil.invalid", "//evil.invalid", "/\\evil.invalid", "/\tevil", "/login", "/team-access?next=/login", "/../login"]) {
    assert.equal(safeNextPath(path), "/classrooms");
  }
  assert.equal(safeNextPath("/tasks/id?from=classroom#evidence"), "/tasks/id?from=classroom#evidence");
});

test("过期登录保留原资源路径，不建立演示会话", () => {
  let destination;
  globalThis.window = { location: { pathname: "/reports/owned-id", search: "?view=preview", hash: "#source", assign: value => { destination = value; } } };
  try {
    redirectToLogin();
    const url = new URL(destination, "https://classroom.invalid");
    assert.equal(url.pathname, "/login");
    assert.equal(url.searchParams.get("next"), "/reports/owned-id?view=preview#source");
  } finally { delete globalThis.window; }
});
