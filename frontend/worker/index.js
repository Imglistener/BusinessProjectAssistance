// Cloudflare Worker: serves the built app (dist/) and forwards /api to the backend, so the app has one address.
// Settings (npx wrangler secret put NAME): BACKEND_URL, e.g. https://bpa-backend.onrender.com, and PROXY_SECRET,
// the same value as on the backend.

// Set only here: whatever a visitor sends under these names is dropped.
const OURS = ["x-proxy-secret", "x-client-ip", "x-forwarded-for", "x-real-ip"];

function unavailable(message) {
  return Response.json({ error: { code: "backend_unavailable", message } }, { status: 503 });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    if (!env.BACKEND_URL || !env.PROXY_SECRET) return unavailable("The server isn't set up yet.");

    const headers = new Headers(request.headers);
    for (const name of OURS) headers.delete(name);
    headers.set("X-Proxy-Secret", env.PROXY_SECRET);
    headers.set("X-Client-IP", request.headers.get("CF-Connecting-IP") ?? "");

    const target = new URL(url.pathname + url.search, env.BACKEND_URL);
    try {
      return await fetch(target, { method: request.method, headers, body: request.body, redirect: "manual" });
    } catch {
      return unavailable("The server can't be reached right now. Try again in a moment.");
    }
  },
};
