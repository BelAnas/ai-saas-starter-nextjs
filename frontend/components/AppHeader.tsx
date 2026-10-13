"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export function AppHeader({ user, children }: { user: User; children?: React.ReactNode }) {
  const router = useRouter();

  async function signOut() {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line bg-panel px-4">
      <Link href="/app" className="flex items-center gap-2 font-semibold">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-sm text-white">S</span>
        Shopdesk AI
      </Link>
      <div className="ml-auto flex items-center gap-4 text-sm">
        {children}
        <nav className="flex items-center gap-3 text-muted">
          <Link href="/app" className="hover:text-ink">Chat</Link>
          <Link href="/app/account" className="hover:text-ink">Account</Link>
          {user.role === "admin" && <Link href="/admin" className="hover:text-ink">Admin</Link>}
        </nav>
        <span className="hidden text-muted sm:inline" title={user.email}>{user.name || user.email}</span>
        <button onClick={signOut} className="rounded-md border border-line px-3 py-1.5 hover:bg-surface">
          Sign out
        </button>
      </div>
    </header>
  );
}
