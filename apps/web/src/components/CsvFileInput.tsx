"use client";
import { FileUp } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { decodeBytes, summariseCsv, type CsvSummary } from "@/lib/csv";

const MAX_BYTES = 5 * 1024 * 1024;

type Picked = { name: string; summary: CsvSummary };

/** A real file input, shown as a button. The file is read in the browser, nothing leaves until the person presses Import. */
export function CsvFileInput({ onText }: { onText: (text: string) => void }) {
  const id = useId();
  const [picked, setPicked] = useState<Picked | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [over, setOver] = useState(false);

  // While this box is on screen a file dropped anywhere else does nothing, instead of the browser leaving the app to show the file.
  useEffect(() => {
    const stop = (e: DragEvent) => { if (e.dataTransfer?.types.includes("Files")) e.preventDefault(); };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => { window.removeEventListener("dragover", stop); window.removeEventListener("drop", stop); };
  }, []);

  async function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) await handle(file);
  }

  async function handle(file: File) {
    setError(null);
    // A file that is refused empties the text box too, so pressing Import cannot send the rows of an earlier file by mistake.
    const refuse = (message: string) => { setPicked(null); setError(message); onText(""); };
    if (file.size > MAX_BYTES) { refuse("That file is over 5 MB. Split it into smaller files."); return; }
    try {
      const text = decodeBytes(await file.arrayBuffer());
      const summary = summariseCsv(text);
      if (summary.rows === 0) { refuse("That file has no data rows. It needs a header row and at least one person."); return; }
      setPicked({ name: file.name, summary });
      onText(text);
    } catch {
      refuse("Could not read that file. Save it as CSV and try again.");
    }
  }

  const s = picked?.summary;
  return (
    <div
      className="sx-field rm-file"
      data-over={over || undefined}
      // Dropping a file on the dialog reads it here. Without this the browser would leave the app and open the file instead.
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) void handle(f); }}
    >
      <span className="sx-label">CSV file</span>
      <div className="rm-file__row">
        <input id={id} type="file" accept=".csv,text/csv,text/plain" className="rm-file__input" onChange={onChange} />
        <label htmlFor={id} className="sx-btn rm-file__btn"><FileUp size={14} aria-hidden />Choose a CSV file</label>
        <span className="rm-file__name">{picked ? picked.name : "No file chosen. You can also drop one here."}</span>
      </div>
      <div role="status" aria-live="polite">
        {error ? <span className="sx-field__error" role="alert">{error}</span> : null}
        {s ? (
          <>
            <p className="rm-file__sum">{s.rows} {s.rows === 1 ? "row" : "rows"}, {s.columns.length} columns. {s.hasPhone ? "Showing the first rows below, and the text box holds the whole file." : "There is no phone column, so no row can be called."}</p>
            <div className="rm-file__scroll" tabIndex={0} aria-label="Preview of the first rows">
              <table className="rm-file__table">
                <caption className="rm-file__cap">First {s.preview.length} of {s.rows}</caption>
                <thead><tr>{s.columns.map((c, i) => <th key={i} scope="col">{c}</th>)}</tr></thead>
                <tbody>{s.preview.map((r, i) => <tr key={i}>{s.columns.map((_, j) => <td key={j}>{r[j] ?? ""}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
