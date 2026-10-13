// Forwards /api/* from the browser to the Python API and streams the answer back.
//
// Why a proxy: the browser then talks to one origin only. The session cookie stays httpOnly and
// first-party, there is no CORS configuration, and the API can sit on a private network.

import { BACKEND_URL } from "@/lib/server";

const REQUEST_HEADERS = ["cookie", "content-type", "accept"];
const RESPONSE_HEADERS = ["content-type", "cache-control", "retry-after", "x-accel-buffering"];

async function forward(request: Request, context: RouteContext<"/api/[...path]">): Promise<Response> {
  const { path } = await context.params;
  const target = `${BACKEND_URL}/api/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`;

  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      // When the visitor presses Stop or closes the tab, this cancels the call to the API too,
      // so the model stops producing tokens nobody will read.
      signal: request.signal,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return Response.json({ detail: "The API is not reachable." }, { status: 502 });
  }

  const out = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);

  // Passing the body through as a stream (not awaiting it) is what keeps answers word by word.
  const hasBody = upstream.status !== 204 && upstream.status !== 304;
  return new Response(hasBody ? upstream.body : null, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PATCH, forward as PUT, forward as DELETE };
