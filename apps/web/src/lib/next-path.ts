/** The page to open after signing in: the `next` value when it is a path on this site, else the overview. A value that would land on another site is dropped. */
export function afterSignIn(search: string, origin: string): string {
  try {
    const next = new URLSearchParams(search).get("next") ?? "";
    // Resolve it against this site: a slash, a tab, then a host name becomes //host once the parser drops the tab, which is another origin.
    const url = new URL(next, origin);
    return next.startsWith("/") && url.origin === origin ? url.pathname + url.search + url.hash : "/";
  } catch {
    return "/";
  }
}
