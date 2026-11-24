// Puts the app online from this computer (docs/hosting.md): runs the backend here, opens a Cloudflare quick tunnel to
// it, and points the Cloudflare Worker at the tunnel. No card and no other account; works while this window is open.
//
//   node scripts/go-online.mjs              (or .\go-online.ps1)
//   node scripts/go-online.mjs --setup      ask for the settings again
//   node scripts/go-online.mjs --no-worker  everything except changing the Worker (for testing)
//
// Settings and secrets are kept in %LOCALAPPDATA%\BusinessProjectAssistance\online.json, outside the repository.
// Keys (Gemini, Groq, Gmail...) come from .env, like the local app; the database is separate from it.
import { spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import readline from "node:readline/promises";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const HOME = process.env.BPA_ONLINE_DIR ?? join(process.env.LOCALAPPDATA ?? process.cwd(), "BusinessProjectAssistance");
const SETTINGS = join(HOME, "online.json");
const CLOUDFLARED = join(HOME, "cloudflared.exe");
const CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe";
const PORT = Number(process.env.BPA_ONLINE_PORT ?? 5100);
const LOCAL = `http://127.0.0.1:${PORT}`;
const WITH_WORKER = !process.argv.includes("--no-worker");

// Only the flask command reads .env by itself. It doesn't replace what's already set, so the settings below win.
const SERVE = [
  "import sys",
  "from dotenv import load_dotenv",
  "load_dotenv('../.env')",
  "from waitress import serve",
  "from wsgi import app",
  "serve(app, host='127.0.0.1', port=int(sys.argv[1]), threads=8)",
].join("\n");

const say = (text) => console.log(`[${new Date().toLocaleTimeString()}] ${text}`);
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const children = new Set();
let stopping = false;

function stop(code = 0) {
  stopping = true;
  // taskkill /T: py.exe starts python.exe, which would otherwise stay behind holding the port.
  for (const child of children) spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  process.exit(code);
}
process.on("SIGINT", () => {
  say("Stopping. The site stays up but shows an error until you run this again.");
  stop();
});
process.on("SIGTERM", () => stop());
process.on("SIGHUP", () => stop()); // the window was closed

function fail(message) {
  console.error(`\n${message}`);
  stop(1);
}

function start(command, args, options, logName) {
  const child = spawn(command, args, { ...options, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
  const log = createWriteStream(join(HOME, "logs", logName), { flags: "w" });
  child.stdout.pipe(log, { end: false });
  child.stderr.pipe(log, { end: false });
  children.add(child);
  child.on("exit", () => children.delete(child));
  child.on("error", (e) => fail(`Couldn't start ${command}: ${e.message}`));
  return child;
}

async function settings() {
  const saved = existsSync(SETTINGS) ? JSON.parse(readFileSync(SETTINGS, "utf8")) : {};
  if (!saved.url || process.argv.includes("--setup")) {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const url = (await rl.question(`Your site's address (https://....workers.dev)${saved.url ? ` [${saved.url}]` : ""}: `)).trim() || saved.url;
    if (!/^https:\/\/[^/\s]+\/?$/.test(url ?? "")) fail("That doesn't look like an address: it should be https://....workers.dev");
    const db = (await rl.question("Neon connection string (Enter to keep the data on this computer): ")).trim();
    rl.close();
    saved.url = url.replace(/\/$/, "");
    if (db) saved.database = db;
    else if (!saved.database) saved.database = `sqlite:///${join(HOME, "online.sqlite").replaceAll("\\", "/")}`;
  }
  // Made once: changing the first two would sign everyone out.
  for (const name of ["SECRET_KEY", "JWT_SECRET_KEY", "PROXY_SECRET"]) saved[name] ??= randomBytes(48).toString("base64url");
  writeFileSync(SETTINGS, JSON.stringify(saved, null, 2));
  return saved;
}

function python(args, options = {}) {
  return spawnSync("py", args, { cwd: join(ROOT, "backend"), encoding: "utf8", windowsHide: true, ...options });
}

async function getCloudflared() {
  if (existsSync(CLOUDFLARED)) return;
  say("Downloading cloudflared from Cloudflare's GitHub releases (once)...");
  const r = await fetch(CLOUDFLARED_URL);
  if (!r.ok) fail(`Couldn't download cloudflared (HTTP ${r.status}).`);
  writeFileSync(CLOUDFLARED, Buffer.from(await r.arrayBuffer()));
}

/** Resolves with the tunnel's address once it's connected. */
function openTunnel() {
  return new Promise((done, failed) => {
    // --config: ignore any config file of another tunnel on this computer (quick tunnels refuse to start with one).
    const child = start(CLOUDFLARED, ["tunnel", "--config", "NUL", "--no-autoupdate", "--url", LOCAL], {}, "tunnel.log");
    let text = "";
    const timer = setTimeout(() => {
      spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
      failed(new Error("no answer from Cloudflare after 60 seconds"));
    }, 60_000);
    const read = (data) => {
      text += data;
      const url = text.match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/)?.[0];
      if (url && /Registered tunnel connection/.test(text)) {
        clearTimeout(timer);
        done({ child, url });
      }
      if (text.length > 100_000) text = text.slice(-10_000);
    };
    child.stdout.on("data", read);
    child.stderr.on("data", read);
    child.on("exit", () => {
      clearTimeout(timer);
      failed(new Error("the tunnel closed"));
    });
  });
}

/** The values go through standard input, so they never appear in a command line or a file. */
function pointWorkerAt(tunnelUrl, secret) {
  const r = spawnSync("npx --yes wrangler@4 secret bulk", {
    cwd: join(ROOT, "frontend"),
    input: JSON.stringify({ BACKEND_URL: tunnelUrl, PROXY_SECRET: secret }),
    encoding: "utf8",
    shell: true,
    windowsHide: true,
  });
  if (r.status !== 0) {
    const reason = `${r.stdout}\n${r.stderr}`;
    return /not authenticated|login/i.test(reason) ? "run `npx wrangler@4 login` in frontend/ first" : reason.trim().slice(-400);
  }
  return null;
}

async function healthy(base, tries, headers = {}) {
  for (let i = 0; i < tries && !stopping; i++) {
    try {
      const r = await fetch(`${base}/api/health`, { headers, signal: AbortSignal.timeout(10_000) });
      if (r.ok && (await r.json()).status === "ok") return true;
    } catch {
      /* not yet */
    }
    await sleep(2000);
  }
  return false;
}

mkdirSync(join(HOME, "logs"), { recursive: true });
const config = await settings();
const env = {
  ...process.env,
  SECRET_KEY: config.SECRET_KEY,
  JWT_SECRET_KEY: config.JWT_SECRET_KEY,
  PROXY_SECRET: config.PROXY_SECRET,
  DATABASE_URL: config.database,
  APP_BASE_URL: config.url,
  CORS_ORIGINS: config.url,
  PROXY_FIX_X_FOR: "0",
  UPLOAD_STORAGE: "database", // moves with the data if the app gets a real host later
  CAPTCHA_ENABLED: "true",
};

if (python(["-c", "import waitress"]).status !== 0) {
  say("Installing waitress, the web server (once)...");
  const r = python(["-m", "pip", "install", "--quiet", "waitress>=3,<4"]);
  if (r.status !== 0) fail(`Couldn't install waitress:\n${r.stderr.slice(-500)}`);
}
await getCloudflared();

say("Updating the database...");
const migrated = python(["-m", "flask", "--app", "wsgi", "db", "upgrade"], { env });
if (migrated.status !== 0) fail(`Couldn't update the database:\n${migrated.stderr.slice(-800)}`);

async function runBackend() {
  while (!stopping) {
    const child = start("py", ["-c", SERVE, String(PORT)], { cwd: join(ROOT, "backend"), env }, "online-backend.log");
    await new Promise((done) => child.on("exit", done));
    if (stopping) return;
    say("The backend stopped; starting it again (details in logs\\online-backend.log).");
    await sleep(3000);
  }
}

if (await healthy(LOCAL, 1)) fail(`Something is already running on port ${PORT}. Is this open in another window?`);
void runBackend();
if (!(await healthy(LOCAL, 30))) fail(`The backend didn't start: see ${join(HOME, "logs", "online-backend.log")}`);
say("Backend running.");

let wait = 5;
while (!stopping) {
  let tunnel;
  try {
    tunnel = await openTunnel();
  } catch (e) {
    say(`Couldn't open the tunnel (${e.message}); trying again in ${wait} s.`);
    await sleep(wait * 1000);
    wait = Math.min(wait * 2, 120); // Cloudflare limits how often tunnels are opened
    continue;
  }
  wait = 5;
  const closed = new Promise((done) => (tunnel.child.exitCode !== null ? done() : tunnel.child.on("exit", done)));
  say("Tunnel open.");
  if (WITH_WORKER) {
    const problem = pointWorkerAt(tunnel.url, config.PROXY_SECRET);
    if (problem) fail(`Couldn't update the Cloudflare Worker: ${problem}`);
    say((await healthy(config.url, 30)) ? `ONLINE: ${config.url}  (Ctrl+C to stop)` : `Started, but ${config.url} doesn't answer yet. Try it in a minute.`);
  } else {
    say(`Tunnel address: ${tunnel.url}  ${(await healthy(tunnel.url, 30)) ? "answers" : "doesn't answer"}`);
  }
  await closed;
  if (!stopping) say("The tunnel closed; opening a new one.");
}
