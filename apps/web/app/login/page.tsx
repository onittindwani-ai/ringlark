"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Field } from "@sendora/ui-kit";
import { api } from "@/lib/api";
import { afterSignIn } from "@/lib/next-path";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const demoHint = process.env.NEXT_PUBLIC_DEMO_HINT === "1";

  async function submit() {
    setError(null);
    try {
      await api("/session", { method: "POST", json: { email, password } });
    } catch (e) {
      setError((e as Error).message);
      throw e;
    }
    router.replace(afterSignIn(window.location.search, window.location.origin));
    router.refresh();
  }

  return (
    <main className="rm-login" id="main">
      <Card className="rm-login__card">
        <div>
          <h1 className="rm-title">Ringlark</h1>
          <p className="rm-sub">Sign in to see your calls, replies and booked meetings.</p>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); }} style={{ display: "grid", gap: 21 }}>
          <Field label="Email" type="email" autoComplete="username" value={email} onChange={setEmail} validate={(v) => (/^\S+@\S+\.\S+$/.test(v) ? null : "Add an @ and a domain, like name@company.com")} />
          <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={setPassword} />
          {error ? <p role="alert" className="sx-field__error" style={{ margin: 0 }}>{error}</p> : null}
          <Button type="submit" variant="primary" disabled={!email || !password} disabledReason="Enter your email and password" onClick={submit}>Sign in</Button>
        </form>
        {demoHint ? <p className="rm-mini" style={{ margin: 0 }}>Demo sign in: owner@example.test with the password demo-password-1. Demo data only.</p> : null}
      </Card>
    </main>
  );
}
