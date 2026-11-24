// Takes the user guide's screenshots (docs/images) in English and French, then run: npm run docs:pdf
// Needs the app running with `flask --app wsgi demo-data` loaded, the captcha off and an AI key; use a scratch database.
// Run: GUIDE_BASE_URL=http://localhost:5174 node scripts/guide-screenshots.mjs
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.GUIDE_BASE_URL ?? "http://localhost:5173";
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/images");
const QUESTION = { en: "Which projects are over budget?", fr: "Quels projets dépassent leur budget ?" };

const browser = await chromium.launch();
for (const lang of ["en", "fr"]) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1.5,
    locale: lang === "fr" ? "fr-FR" : "en-GB",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const shot = async (name, target = page) => {
    await page.mouse.move(640, 799);
    await page.waitForTimeout(2000); // fonts, counters and fades settle
    await target.screenshot({ path: join(OUT, `${lang}-${name}.jpg`), type: "jpeg", quality: 88 });
    console.log(`${lang}-${name}.jpg`);
  };

  await page.goto(`${BASE}/login`);
  await page.evaluate((l) => localStorage.setItem("bpa.lang", l), lang);
  await page.reload();
  await page.fill("#email", "demo@example.com");
  await page.fill("#password", "demo-password");
  await page.click("button[type=submit]");
  await page.waitForURL(/\/app/);

  await page.waitForSelector("a[href^='/app/projects/']");
  await shot("dashboard");

  await page.goto(`${BASE}/app/projects/1`);
  await page.waitForSelector(".main__header h1");
  await shot("project");

  await page.goto(`${BASE}/app`);
  await page.locator("a[href^='/app/projects/']", { hasText: "Office move" }).first().click();
  await page.locator("a[href*='/trips/']", { hasText: "Furniture pickup" }).first().click();
  const fuel = page.locator("section", { has: page.locator(".fuel__ask") }).last();
  await fuel.waitFor();
  await shot("trip-fuel", fuel);

  await page.goto(`${BASE}/app/inventory`);
  await page.waitForSelector("text=Printer paper A4");
  await shot("inventory");

  await page.goto(`${BASE}/app`);
  await page.waitForSelector("a[href^='/app/projects/']");
  await page.locator("[data-slot=sidebar-inset] > header button[aria-pressed]").click();
  const panel = page.locator("aside.assistant-panel");
  await panel.locator("button.model-picker").waitFor();
  await shot("assistant");

  // Again if the other AI had to step in: the picture shows the usual case.
  for (let i = 0; i < 4; i++) {
    await panel.locator("#chat-input").fill(QUESTION[lang]);
    await panel.locator("#chat-input").press("Enter");
    await panel.locator(".bubble--ai").waitFor({ timeout: 180_000 });
    if ((await panel.locator(".chat__draft-note").count()) === 0) break;
    await page.waitForTimeout(10_000);
    await panel.locator(".assistant-panel__tools button").nth(1).click(); // new conversation
  }
  await panel.locator(".chat__log").evaluate((log) => (log.scrollTop = 0)); // the question too
  await panel.locator("button.model-picker").click();
  await page.waitForSelector("[role=menuitemradio]");
  await shot("assistant-answer", panel);
  await context.close();
}
await browser.close();
