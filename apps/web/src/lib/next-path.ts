/** The page to open after signing in: the `next` value when it is a path on this site, else the overview. A value that would land on another site is dropped.
 *
 * The browser (and `router.replace`) read `//host` as another site, so the answer is checked AFTER the address has been resolved, not only before: `/a/..//evil.example`
 * has dots that resolve to `//evil.example`, which a check on the raw text would let through. */
export function afterSignIn(search: string, origin: string): string {
  const next = new URLSearchParams(search).get("next") ?? "";
  // Only a plain path: it starts with one slash, and holds no backslash, no control character (a tab or newline inside "//" is dropped by the URL parser) and no scheme.
  if (!next.startsWith("/") || next.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(next)) return "/";
  try {
    const url = new URL(next, origin);
    if (url.origin !== origin) return "/";
    const path = url.pathname + url.search + url.hash;
    // After dot segments are resolved a path can start with "//" again, and "/\" is read as "//" too.
    return path.startsWith("//") || path.startsWith("/\\") ? "/" : path;
  } catch {
    return "/";
  }
}
