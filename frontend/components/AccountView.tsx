"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDay, formatNumber, formatTime } from "@/lib/format";
import type { AccountUsage, User } from "@/lib/types";
import { AppHeader } from "./AppHeader";

function Bar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const ratio = Math.min(1, used / Math.max(1, limit));
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="tabular-nums">
          <span className="font-medium">{formatNumber(used)}</span> of {formatNumber(limit)}
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line">
        <div className={`h-full rounded-full ${ratio >= 1 ? "bg-danger" : ratio >= 0.8 ? "bg-warn" : "bg-accent"}`}
          style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}

export function AccountView({ user }: { user: User }) {
  const router = useRouter();
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AccountUsage>("/api/account/usage").then(setUsage).catch(() => undefined);
  }, []);

  async function deleteAccount(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const password = new FormData(event.currentTarget).get("password");
    if (!window.confirm("Delete your account and all saved conversations? This cannot be undone.")) return;
    try {
      await api("/api/account/delete", { json: { password } });
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The request failed.");
    }
  }

  const card = "rounded-xl border border-line bg-panel p-6";
  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader user={user} />
      <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
        <h1 className="text-2xl font-semibold">Account</h1>

        <section className={card}>
          <div className="flex items-baseline justify-between">
            <h2 className="font-semibold">{user.name || user.email}</h2>
            <span className="text-sm text-muted">{user.email}</span>
          </div>
          {usage && (
            <div className="mt-5 space-y-4">
              <p className="text-sm">
                Plan: <span className="font-medium">{usage.plan.label}</span>
                <span className="text-muted">
                  {" "}· ${usage.plan.price_usd_month} / month · allowance resets at {formatTime(usage.quota.resets_at)} (midnight UTC)
                </span>
              </p>
              <Bar label="Messages today" used={usage.quota.messages_used} limit={usage.quota.messages_limit} />
              <Bar label="Tokens today" used={usage.quota.tokens_used} limit={usage.quota.tokens_limit} />
            </div>
          )}
        </section>

        {usage && (
          <section className={card}>
            <h2 className="font-semibold">Last 7 days</h2>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th className="py-1 font-normal">Day</th>
                  <th className="py-1 text-right font-normal">Messages</th>
                  <th className="py-1 text-right font-normal">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {usage.last_7_days.map((d) => (
                  <tr key={d.date} className="border-t border-line">
                    <td className="py-1.5">{formatDay(d.date)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(d.messages)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(d.tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <section className={card}>
          <h2 className="font-semibold text-danger">Delete account</h2>
          <p className="mt-1 text-sm text-muted">
            Removes your account, your sessions and every saved conversation. Type your password to confirm.
          </p>
          <form onSubmit={deleteAccount} className="mt-4 flex gap-2">
            <input name="password" type="password" required placeholder="Password" autoComplete="current-password"
              className="flex-1 rounded-md border border-line bg-panel px-3 py-2 outline-none focus:border-danger" />
            <button className="rounded-md border border-danger px-4 py-2 text-sm font-medium text-danger hover:bg-red-50">
              Delete my account
            </button>
          </form>
          {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
        </section>
      </main>
    </div>
  );
}
