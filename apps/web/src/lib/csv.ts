/** A small CSV reader for the import preview. The server does the real parsing and checking. */

export type CsvSummary = { columns: string[]; rows: number; preview: string[][]; hasPhone: boolean };

/** The most people one import takes. The server refuses more, so the screen says so before sending. */
export const MAX_IMPORT_ROWS = 5000;

/** Excel in many countries saves "CSV" with semicolons, and some tools use tabs. Pick the separator the header row uses most. */
export function detectDelimiter(text: string): string {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const head = src.split(/\r\n|\n|\r/, 1)[0] ?? "";
  let best = ",";
  let bestCount = 0;
  for (const d of [",", ";", "\t"]) {
    const n = head.split(d).length - 1;
    if (n > bestCount) { best = d; bestCount = n; }
  }
  return best;
}

export function parseCsv(text: string, delimiter: string = detectDelimiter(text)): string[][] {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]!;
    if (quoted) {
      if (ch === '"' && src[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delimiter) { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      rows.push(row); row = [];
    } else cell += ch;
  }
  if (cell !== "" || row.length > 0) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

export function summariseCsv(text: string, previewRows = 5): CsvSummary {
  const all = parseCsv(text);
  const columns = (all[0] ?? []).map((c) => c.trim());
  return {
    columns,
    rows: Math.max(0, all.length - 1),
    preview: all.slice(1, 1 + previewRows),
    hasPhone: columns.some((c) => c.toLowerCase() === "phone"),
  };
}

/** The rows the server receives: one object per person, keyed by the lower case header names. Empty lines are dropped. */
export function toRows(text: string): Record<string, string>[] {
  const [head = [], ...lines] = parseCsv(text);
  const cols = head.map((c) => c.trim().toLowerCase());
  return lines.filter((l) => l.some((v) => v.trim())).map((l) => Object.fromEntries(l.map((v, i) => [cols[i] ?? `col${i}`, v.trim()])));
}

/** Why the Import button must stay off, or null when the text can be sent. */
export function importBlocker(text: string): string | null {
  const s = summariseCsv(text);
  if (s.rows === 0) return "Choose a file or paste at least one person under a header row";
  if (!s.hasPhone) return "There is no phone column, so no one could be called";
  if (s.rows > MAX_IMPORT_ROWS) return `That is ${s.rows} people. Import up to ${MAX_IMPORT_ROWS} at a time`;
  return null;
}

/** Read a chosen file as text. Strict UTF-8 first; a file saved by older Windows tools (Latin 1) is read as Windows 1252 so accents survive. */
export function decodeBytes(bytes: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1252").decode(bytes);
  }
}
