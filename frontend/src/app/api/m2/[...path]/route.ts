import { proxyAuthenticatedJson } from "@/lib/server/backend";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context) {
  const { path } = await context.params;
  return proxyAuthenticatedJson(
    request,
    `/api/${path.map(encodeURIComponent).join("/")}`,
  );
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
