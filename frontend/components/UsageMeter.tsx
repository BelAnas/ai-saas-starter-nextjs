import type { Quota } from "@/lib/types";

/** Compact "7 / 20 today" meter. Turns amber near the limit and red at it. */
export function UsageMeter({ quota }: { quota: Quota | null }) {
  if (!quota) return null;
  const ratio = Math.min(1, quota.messages_used / Math.max(1, quota.messages_limit));
  const color = ratio >= 1 ? "bg-danger" : ratio >= 0.8 ? "bg-warn" : "bg-accent";
  return (
    <div className="flex items-center gap-2" data-testid="usage-meter" title={`Resets at ${new Date(quota.resets_at).toLocaleTimeString()}`}>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${ratio * 100}%` }} />
      </div>
      <span className="tabular-nums text-muted">
        <span className="font-medium text-ink">{quota.messages_used}</span> / {quota.messages_limit} today
      </span>
      <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-accent">
        {quota.plan}
      </span>
    </div>
  );
}
