import Link from "next/link";
import { formatNumber } from "@/lib/format";
import { BACKEND_URL } from "@/lib/server";
import type { Plan } from "@/lib/types";

// The plan table is read from the API on each request, so the page always shows the limits the
// server really enforces.
export const dynamic = "force-dynamic";

async function getPlans(): Promise<Plan[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/plans`, { cache: "no-store" });
    return response.ok ? await response.json() : [];
  } catch {
    return [];
  }
}

const EXAMPLES = [
  ["Product descriptions", "Turn a few notes about an item into a clear listing with the details shoppers look for."],
  ["Customer replies", "Draft a calm, specific answer to a late parcel, a return request or a complaint."],
  ["FAQ entries", "Write the shipping, returns and care answers once, in the tone of your shop."],
];

export default async function Landing() {
  const plans = await getPlans();
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6">
      <header className="flex items-center justify-between py-6">
        <span className="flex items-center gap-2 text-lg font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-accent text-white">S</span>
          Shopdesk AI
        </span>
        <nav className="flex items-center gap-3 text-sm">
          <Link href="/login" className="px-3 py-2 text-muted hover:text-ink">Sign in</Link>
          <Link href="/register" className="rounded-md bg-accent px-4 py-2 font-medium text-white hover:opacity-90">
            Start free
          </Link>
        </nav>
      </header>

      <section className="py-16 text-center">
        <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          The writing assistant for small online shops
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted">
          Product descriptions, customer replies and FAQ entries, drafted in seconds and saved so you can come
          back to them.
        </p>
        <Link href="/register" className="mt-8 inline-block rounded-md bg-accent px-6 py-3 font-medium text-white hover:opacity-90">
          Create a free account
        </Link>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {EXAMPLES.map(([title, text]) => (
          <div key={title} className="rounded-xl border border-line bg-panel p-5">
            <h2 className="font-semibold">{title}</h2>
            <p className="mt-2 text-sm text-muted">{text}</p>
          </div>
        ))}
      </section>

      {plans.length > 0 && (
        <section className="py-16">
          <h2 className="text-center text-2xl font-semibold">Plans</h2>
          <div className="mx-auto mt-8 grid max-w-2xl gap-4 sm:grid-cols-2">
            {plans.map((plan) => (
              <div key={plan.name} className="rounded-xl border border-line bg-panel p-6">
                <h3 className="font-semibold">{plan.label}</h3>
                <p className="mt-2 text-3xl font-semibold">
                  ${plan.price_usd_month}
                  <span className="text-base font-normal text-muted"> / month</span>
                </p>
                <ul className="mt-4 space-y-2 text-sm text-muted">
                  <li>{formatNumber(plan.daily_messages)} messages per day</li>
                  <li>{formatNumber(plan.daily_tokens)} tokens per day</li>
                  <li>Answers up to {formatNumber(plan.max_output_tokens)} tokens</li>
                  <li>Saved history</li>
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-4 text-center text-xs text-muted">
            Demo product. There is no payment step: an administrator changes the plan of an account.
          </p>
        </section>
      )}
    </main>
  );
}
