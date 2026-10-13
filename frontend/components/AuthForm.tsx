"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api(`/api/auth/${mode}`, {
        json: { email: form.get("email"), password: form.get("password"), name: form.get("name") ?? "" },
      });
      router.push("/app");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Is the API running?");
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border border-line bg-panel px-3 py-2 outline-none focus:border-accent";
  return (
    <main className="grid flex-1 place-items-center px-4 py-12">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2 text-lg font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-accent text-white">S</span>
          Shopdesk AI
        </Link>
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-panel p-6 shadow-sm">
          <h1 className="text-xl font-semibold">{isRegister ? "Create your account" : "Sign in"}</h1>
          {isRegister && (
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Name</span>
              <input name="name" className={input} autoComplete="name" maxLength={80} />
            </label>
          )}
          <label className="block text-sm">
            <span className="mb-1 block text-muted">Email</span>
            <input name="email" type="email" required className={input} autoComplete="email" />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-muted">Password{isRegister && " (8 characters or more)"}</span>
            <input
              name="password" type="password" required minLength={isRegister ? 8 : 1} className={input}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </label>
          {error && <p role="alert" className="rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">{error}</p>}
          <button disabled={busy} className="w-full rounded-md bg-accent py-2 font-medium text-white hover:opacity-90 disabled:opacity-60">
            {busy ? "Please wait..." : isRegister ? "Create account" : "Sign in"}
          </button>
          <p className="text-center text-sm text-muted">
            {isRegister ? "Already have an account? " : "New here? "}
            <Link href={isRegister ? "/login" : "/register"} className="font-medium text-accent hover:underline">
              {isRegister ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </form>
        {!isRegister && (
          <p className="mt-4 text-center text-xs text-muted">
            Demo data: <code>demo@example.com</code> / <code>demo-demo-1</code>, or{" "}
            <code>admin@example.com</code> / <code>admin-demo-1</code>
          </p>
        )}
      </div>
    </main>
  );
}
