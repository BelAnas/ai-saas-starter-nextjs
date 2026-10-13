// Server-side helpers. This file must only be imported from server components and route handlers.

import { cookies } from "next/headers";
import type { User } from "./types";

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

/**
 * Ask the API who the visitor is, using their cookies. The API is the only judge of a session:
 * the web server never decodes or trusts the cookie itself.
 */
export async function getCurrentUser(): Promise<User | null> {
  const jar = await cookies();
  const header = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  if (!header) return null;
  try {
    const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
      headers: { cookie: header },
      cache: "no-store",
    });
    return response.ok ? ((await response.json()) as User) : null;
  } catch {
    return null; // API down: treated as signed out, the sign-in page will show the error
  }
}
