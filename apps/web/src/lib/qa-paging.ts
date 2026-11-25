/** The QA queue is read a page at a time with an offset. The server refuses a page size over 1000, so the page must never ask for "everything so far" (a limit that grows
 *  with each click used to fail on the eleventh click, and a call beyond that could not be marked as read). */
export const QA_PAGE = 100;

export function qaPageUrl(show: "open" | "all", page: number): string {
  const n = Number.isInteger(page) && page > 0 ? page : 0;
  return `/qa?show=${show}&limit=${QA_PAGE}&offset=${n * QA_PAGE}`;
}

/** Is there probably another page? A full page says yes. */
export function hasMore(lastPageLength: number): boolean {
  return lastPageLength >= QA_PAGE;
}
