"use client";
import { Button, Card } from "@sendora/ui-kit";

/** Shown when a page fails while it draws. The person can try again without losing their place. */
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="rm-login" id="main">
      <Card className="rm-login__card">
        <div role="alert">
          <h1 className="rm-title">Something went wrong</h1>
          <p className="rm-sub">This page could not be shown. Nothing was changed. Try again, and if it keeps happening check that the API is running.</p>
        </div>
        <Button variant="primary" onClick={() => reset()}>Try again</Button>
      </Card>
    </main>
  );
}
