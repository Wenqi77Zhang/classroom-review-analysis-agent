import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const loginPage = read("src/app/login/page.tsx");
const loginRoute = read("src/app/api/session/login/route.ts");
const logoutRoute = read("src/app/api/session/logout/route.ts");
const meRoute = read("src/app/api/session/me/route.ts");
const chrome = read("src/components/baseline/SiteChrome.tsx");
const classroom = read("src/components/baseline/ClassroomBaseline.tsx");
const classroomRoute = read("src/app/api/classrooms/[classroomId]/route.ts");

assert.doesNotMatch(loginPage, /TODO：登录页面/);
assert.match(loginPage, /教师邮箱/);
assert.match(loginPage, /current-password/);
assert.match(loginPage, /受控演示账号/);
assert.match(loginPage, /HttpOnly/);
assert.match(loginRoute, /requestCameFromSameOrigin/);
assert.match(loginRoute, /consumeAttempt/);
assert.match(loginRoute, /setAuthCookie/);
assert.match(logoutRoute, /clearAuthCookie/);
assert.match(meRoute, /proxyAuthenticatedJson/);
assert.match(chrome, /classroom-session-changed/);
assert.match(chrome, /退出当前账号/);
assert.match(classroom, /我的已有课堂/);
assert.match(classroom, /确认永久删除/);
assert.match(classroomRoute, /export async function DELETE/);

console.log("AUTH_SESSION_CONTRACT_OK");
