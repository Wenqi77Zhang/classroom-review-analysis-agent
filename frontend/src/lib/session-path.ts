const FALLBACK = "/classrooms";

export function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || /[\\\u0000-\u0020\u007f]/.test(value)) return FALLBACK;
  try {
    const base = "https://classroom.invalid";
    const url = new URL(value, base);
    if (url.origin !== base || /^\/(login|team-access)(\/|$)/.test(url.pathname)) return FALLBACK;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return FALLBACK;
  }
}

export function redirectToLogin(): void {
  if (typeof window !== "undefined") {
    const next = safeNextPath(`${window.location.pathname}${window.location.search}${window.location.hash}`);
    window.location.assign(`/login?${new URLSearchParams({ next })}`);
  }
}
