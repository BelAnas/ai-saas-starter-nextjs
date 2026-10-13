"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatDay, formatNumber, formatUsd } from "@/lib/format";
import type { AdminOverview, AdminUser, User } from "@/lib/types";
import { AppHeader } from "./AppHeader";
import { METRICS, UsageChart, type Metric } from "./UsageChart";

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const fetchAdminData = () =>
  Promise.all([api<AdminOverview>("/api/admin/overview?days=14"), api<AdminUser[]>("/api/admin/users")]);

export function AdminDashboard({ user }: { user: User }) {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [metric, setMetric] = useState<Metric>("messages");
  const [error, setError] = useState<string | null>(null);

  const show = ([o, u]: [AdminOverview, AdminUser[]]) => {
    setOverview(o);
    setUsers(u);
  };
  const fail = (err: unknown) =>
    setError(err instanceof ApiError ? err.message : "Could not load the admin data.");

  useEffect(() => {
    fetchAdminData().then(show, fail);
  }, []);

  async function patch(id: number, change: { plan?: string; is_active?: boolean }) {
    setError(null);
    try {
      await api(`/api/admin/users/${id}`, { method: "PATCH", json: change });
      show(await fetchAdminData());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change failed.");
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader user={user} />
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
        <div>
          <h1 className="text-2xl font-semibold">Usage and cost</h1>
          <p className="mt-1 text-sm text-muted">
            Computed from the same usage records that enforce the limits. Days are UTC.
          </p>
        </div>
        {error && <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}

        {overview && (
          <>
            <section className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="admin-tiles">
              <Tile label="Accounts" value={formatNumber(overview.totals.users)}
                hint={overview.plans.map((p) => `${p.users} ${p.plan}`).join(" · ")} />
              <Tile label="Messages today" value={formatNumber(overview.today.messages)}
                hint={`${overview.today.active_users} active users`} />
              <Tile label={`Messages, ${overview.days} days`} value={formatNumber(overview.totals.messages)}
                hint={`${overview.totals.failed_requests} failed requests`} />
              <Tile label={`Model cost, ${overview.days} days`} value={formatUsd(overview.totals.cost_usd)}
                hint="Estimate from token counts" />
              <Tile label="Plan revenue / month" value={formatUsd(overview.totals.monthly_revenue_usd)}
                hint="At list price, no payments taken" />
            </section>

            <section className="rounded-xl border border-line bg-panel p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-semibold">{METRICS[metric].label} per day</h2>
                <div className="flex rounded-md border border-line p-0.5 text-sm" role="tablist">
                  {(Object.keys(METRICS) as Metric[]).map((key) => (
                    <button key={key} role="tab" aria-selected={metric === key} onClick={() => setMetric(key)}
                      className={`rounded px-3 py-1 ${metric === key ? "bg-accent-soft font-medium text-accent" : "text-muted hover:text-ink"}`}>
                      {METRICS[key].label}
                    </button>
                  ))}
                </div>
              </div>
              <UsageChart series={overview.series} metric={metric} />
              <details className="mt-2 text-sm">
                <summary className="cursor-pointer text-muted">Show as table</summary>
                <table className="mt-2 w-full">
                  <thead>
                    <tr className="text-left text-muted">
                      <th className="py-1 font-normal">Day</th>
                      <th className="py-1 text-right font-normal">Messages</th>
                      <th className="py-1 text-right font-normal">Tokens</th>
                      <th className="py-1 text-right font-normal">Model cost</th>
                      <th className="py-1 text-right font-normal">Active users</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.series.map((d) => (
                      <tr key={d.date} className="border-t border-line tabular-nums">
                        <td className="py-1">{formatDay(d.date)}</td>
                        <td className="py-1 text-right">{formatNumber(d.messages)}</td>
                        <td className="py-1 text-right">{formatNumber(d.tokens)}</td>
                        <td className="py-1 text-right">{formatUsd(d.cost_usd)}</td>
                        <td className="py-1 text-right">{d.active_users}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </section>
          </>
        )}

        <section className="overflow-x-auto rounded-xl border border-line bg-panel">
          <h2 className="px-5 pt-5 font-semibold">Accounts, by model cost over 30 days</h2>
          <table className="mt-3 w-full text-sm" data-testid="admin-users">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="px-5 py-2 font-normal">Account</th>
                <th className="px-3 py-2 font-normal">Plan</th>
                <th className="px-3 py-2 text-right font-normal">Today</th>
                <th className="px-3 py-2 text-right font-normal">Messages, 30 d</th>
                <th className="px-3 py-2 text-right font-normal">Tokens, 30 d</th>
                <th className="px-3 py-2 text-right font-normal">Cost, 30 d</th>
                <th className="px-3 py-2 font-normal">Last used</th>
                <th className="px-5 py-2 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={`border-b border-line last:border-0 ${u.is_active ? "" : "text-muted"}`}>
                  <td className="px-5 py-2.5">
                    <div className="font-medium">{u.name || u.email}</div>
                    <div className="text-xs text-muted">{u.email}{u.role === "admin" && " · admin"}</div>
                  </td>
                  <td className="px-3 py-2.5">
                    <select value={u.plan} aria-label={`Plan of ${u.email}`}
                      onChange={(e) => void patch(u.id, { plan: e.target.value })}
                      className="rounded-md border border-line bg-panel px-2 py-1">
                      <option value="free">Free</option>
                      <option value="pro">Pro</option>
                    </select>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{u.messages_today} / {u.messages_limit}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(u.messages_30d)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(u.tokens_30d)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatUsd(u.cost_30d_usd)}</td>
                  <td className="px-3 py-2.5 text-muted">{u.last_used_at ? formatDateTime(u.last_used_at) : "never"}</td>
                  <td className="px-5 py-2.5">
                    <button onClick={() => void patch(u.id, { is_active: !u.is_active })} disabled={u.id === user.id}
                      className="rounded-md border border-line px-2 py-1 text-xs hover:bg-surface disabled:opacity-40">
                      {u.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  );
}
