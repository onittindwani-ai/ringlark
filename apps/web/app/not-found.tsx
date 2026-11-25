import Link from "next/link";
import { Card } from "@sendora/ui-kit";

/** Shown for an address that does not exist. */
export default function NotFound() {
  return (
    <main className="rm-login" id="main">
      <Card className="rm-login__card">
        <div>
          <h1 className="rm-title">That page does not exist</h1>
          <p className="rm-sub">The address may be old or mistyped.</p>
        </div>
        <Link href="/" className="sx-btn sx-btn--primary">Go to the overview</Link>
      </Card>
    </main>
  );
}
