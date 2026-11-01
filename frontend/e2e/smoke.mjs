// End-to-end smoke test: drives the running app in a headless browser.
//
// Needs the backend (with `flask --app wsgi demo-data` loaded) and the frontend running.
// Run: npm run e2e            (default http://localhost:5173)
//      E2E_BASE_URL=http://127.0.0.1:5174 npm run e2e
// First time only: npx playwright install chromium-headless-shell
//
// It changes data (receives stock, plans a trip...), so use a scratch database, not real data.
import { chromium } from "playwright";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const errors = [];
let passed = 0;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on("pageerror", (e) => errors.push(`${page.url()}: ${e.message}`));
page.on("console", (m) => {
  // Expected API refusals (e.g. the rejected upload below) also log a failed request; ignore those.
  if (m.type() === "error" && !/status of 4\d\d/.test(m.text())) errors.push(`${page.url()}: ${m.text()}`);
});

async function step(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`  ok  ${name}`);
  } catch (e) {
    console.log(`  FAIL ${name}\n       ${e.message.split("\n")[0]}`);
    await browser.close();
    process.exit(1);
  }
}

console.log(`Smoke test against ${BASE}`);

await step("public page explains the product and links to sign-up", async () => {
  await page.goto(`${BASE}/`);
  await page.waitForSelector("text=From a customer’s request to a planned, budgeted project.");
  await page.waitForSelector("#features-title");
  if (!(await page.locator("a[href='/signup']").count())) throw new Error("no sign-up link");
});

await step("log in as the demo owner", async () => {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", "demo@example.com");
  await page.fill("#password", "demo-password");
  await page.click("button[type=submit]");
  await page.waitForURL("**/app");
});

await step("dashboard shows totals, deadlines and projects", async () => {
  await page.waitForSelector("#agenda-title");
  await page.waitForSelector("text=Website redesign");
  await page.waitForSelector("text=Projects over budget");
  await page.waitForSelector("text=Budget used in MAD");
});

await step("project page shows budget, milestones, tasks, expenses and activity", async () => {
  await page.click(".project-name >> text=Website redesign");
  await page.waitForSelector("text=Over budget by 3,600.00 MAD");
  for (const id of ["#milestones-heading", "#tasks-heading", "#expenses-heading", "#activity-heading"]) {
    await page.waitForSelector(id);
  }
});

await step("receipts: a disguised file is refused, a PDF is attached", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bpa-e2e-"));
  const fake = join(dir, "fake.pdf");
  const real = join(dir, "receipt.pdf");
  writeFileSync(fake, "<html><script>alert(1)</script></html>");
  writeFileSync(real, "%PDF-1.4\n%%EOF\n");
  const row = page.locator("li", { hasText: "Booking plugin" }).first();
  await row.getByRole("button", { name: "Add receipt" }).click();
  await row.locator("input[type=file]").setInputFiles(fake);
  await row.locator("text=Upload a PDF, JPEG, PNG or WebP file.").waitFor();
  await row.locator("input[type=file]").setInputFiles(real);
  await row.getByRole("button", { name: "Receipts (1)" }).waitFor();
});

await step("report renders with figures and definitions", async () => {
  await page.click("text=Report");
  await page.waitForSelector("text=Spending by category");
  await page.waitForSelector("text=How figures are calculated");
});

await step("inventory: receive stock clears the low-stock warning", async () => {
  await page.goto(`${BASE}/app/inventory`);
  const paper = page.locator("li", { hasText: "Printer paper A4" }).first();
  await paper.locator("text=Low stock").waitFor();
  await paper.getByRole("button", { name: "Receive" }).click();
  await page.fill("#move_qty", "10");
  await page.getByRole("dialog").getByRole("button", { name: "Receive stock" }).click();
  await paper.locator("text=14").first().waitFor();
  await page.waitForTimeout(300);
  if (await paper.locator("text=Low stock").count()) throw new Error("still marked low stock");
});

await step("inventory: a stock count records the difference", async () => {
  await page.getByRole("button", { name: "Stock count" }).click();
  await page.fill("[aria-label='Counted pcs of Office chair']", "7");
  await page.click("text=Save count (1)");
  await page.waitForSelector("text=1 item counted, 1 different from the records.");
  await page.waitForSelector("text=-1 pcs");
  await page.getByRole("dialog").getByRole("button", { name: "Done" }).click();
});

await step("warehouses: add one and transfer stock into it", async () => {
  await page.getByRole("tab", { name: /Warehouses/ }).click();
  await page.getByRole("button", { name: "Add warehouse" }).first().click();
  await page.fill("#warehouse_name", "E2E depot");
  await page.fill("#warehouse_address", "Ain Sebaa, Casablanca");
  await page.click("text=Save warehouse");
  await page.waitForSelector(".warehouse-name >> text=E2E depot");
  await page.getByRole("tab", { name: /Items/ }).click();
  const paper = page.locator("li", { hasText: "Printer paper A4" }).first();
  await paper.getByRole("button", { name: "Transfer" }).click();
  await page.click("#transfer_to");
  await page.getByRole("option", { name: /E2E depot/ }).click();
  await page.fill("#transfer_qty", "4");
  await page.getByRole("dialog").getByRole("button", { name: "Transfer" }).click();
  await paper.locator("text=E2E depot · 4").waitFor();
});

await step("project inventory: open it from the project and add an item", async () => {
  await page.goto(`${BASE}/app`);
  await page.click(".project-name >> text=Website redesign");
  await page.locator("#project-inventory-heading").waitFor();
  await page.locator("section[aria-labelledby=project-inventory-heading] a").click();
  await page.waitForURL(/scope=\d+/);
  await page.getByRole("button", { name: "Add item" }).click();
  await page.fill("#item_name", "Roll-up banner");
  await page.fill("#item_quantity", "3");
  await page.getByRole("dialog").getByRole("button", { name: "Add item" }).click();
  await page.waitForSelector(".item-name >> text=Roll-up banner");
});

await step("trips: plan a trip and add an itinerary item", async () => {
  await page.goto(`${BASE}/app`);
  await page.click(".project-name >> text=Website redesign");
  await page.click("text=Plan a trip");
  await page.fill("[name='trip_title']", "E2E supplier visit");
  await page.fill("[name='trip_destination']", "Tangier");
  const start = new Date(Date.now() + 20 * 864e5).toISOString().slice(0, 10);
  await page.fill("[name='trip_start']", start);
  await page.click("text=Create trip");
  await page.click("text=E2E supplier visit");
  await page.click("text=Add to itinerary");
  await page.fill("[name='ti_title']", "Factory tour");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.waitForSelector("text=Factory tour");
});

await step("trips: route and fuel estimate show a cost range", async () => {
  await page.goto(`${BASE}/app`);
  await page.click(".project-name >> text=Office move to Casablanca");
  await page.click("text=Furniture pickup");
  await page.waitForSelector("#route-heading");
  await page.waitForSelector(".fuel__value");
  await page.waitForSelector("text=likely between");
  await page.click("text=How this is calculated");
  await page.waitForSelector("text=Van (diesel)");
});

await step("settings: fuel prices are listed", async () => {
  await page.goto(`${BASE}/app/settings`);
  await page.waitForSelector("#fuel-heading");
  await page.waitForSelector("text=Any city (default)");
});

await step("notifications: badge and page", async () => {
  await page.waitForSelector("[data-sidebar=menu-badge]");
  await page.click("text=Notifications");
  await page.waitForSelector(".note");
});

await step("members and assistant pages load", async () => {
  await page.click("text=Members");
  await page.waitForSelector("#members-heading");
  await page.click("text=Assistant");
  await page.waitForSelector("text=Try one of these");
});

await browser.close();
if (errors.length) {
  console.log(`\nBrowser errors:\n  ${errors.join("\n  ")}`);
  process.exit(1);
}
console.log(`\n${passed} steps passed, no browser errors.`);
