// Builds the user guide PDFs from docs/user-guide.md (English) and docs/user-guide.fr.md (French).
// Run: npm run docs:pdf   -> docs/user-guide-en.pdf, docs/user-guide-fr.pdf
// Uses the Playwright browser installed for the end-to-end tests (npx playwright install chromium-headless-shell).
import { readFileSync, writeFileSync, unlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { marked } from "marked";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const docs = resolve(here, "../../docs");
const fonts = resolve(here, "../node_modules/@fontsource-variable");

const GUIDES = [
  {
    lang: "en",
    source: "user-guide.md",
    out: "user-guide-en.pdf",
    title: "User guide",
    contents: "Contents",
    footer: "BusinessProjectAssistance user guide",
    locale: "en-GB",
  },
  {
    lang: "fr",
    source: "user-guide.fr.md",
    out: "user-guide-fr.pdf",
    title: "Guide d'utilisation",
    contents: "Sommaire",
    footer: "Guide d'utilisation BusinessProjectAssistance",
    locale: "fr-FR",
  },
];

/** Sections (1-based, in order) that start on a new page: getting started, dashboard, projects, inventory, assistant, notifications. */
const NEW_PAGE = new Set([1, 3, 4, 5, 6, 7]);

/** French typography: a non-breaking space before : ; ? ! and inside « », so the mark never starts a line. */
const frenchSpacing = (html) =>
  html.replace(/>([^<]+)</g, (_, text) => `>${text.replace(/ ([:;?!»])/g, " $1").replace(/« /g, "« ")}<`);

const slug = (text) =>
  text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

function render(guide) {
  const markdown = readFileSync(join(docs, guide.source), "utf8");
  // The Markdown's own "# Title" is replaced by the cover.
  const body = markdown.replace(/^# .*\n/, "");
  const sections = [];
  const renderer = new marked.Renderer();
  renderer.heading = ({ tokens, depth }) => {
    const text = marked.Parser.parseInline(tokens);
    const plain = text.replace(/<[^>]+>/g, "");
    const id = slug(plain);
    if (depth === 2) sections.push({ id, text: plain });
    const cls = depth === 2 && NEW_PAGE.has(sections.length) ? ' class="new-page"' : "";
    return `<h${depth} id="${id}"${cls}>${text}</h${depth}>\n`;
  };
  renderer.image = ({ href, text }) =>
    `<figure><img src="${href}" alt="${text}"><figcaption>${text}</figcaption></figure>`;
  const parsed = marked.parse(body, { renderer });
  const html = guide.lang === "fr" ? frenchSpacing(parsed) : parsed;
  // The first paragraph introduces the guide: it goes on the cover.
  const [intro, rest] = splitFirst(html);
  const date = new Intl.DateTimeFormat(guide.locale, { month: "long", year: "numeric" }).format(new Date());
  const toc = sections.map((s) => `<li><a href="#${s.id}">${s.text}</a></li>`).join("");

  return `<!DOCTYPE html>
<html lang="${guide.lang}">
<head>
<meta charset="utf-8">
<title>${guide.title} — BusinessProjectAssistance</title>
<base href="${pathToFileURL(docs + "/").href}">
<style>
@font-face { font-family: "Bricolage"; src: url("${pathToFileURL(join(fonts, "bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2")).href}") format("woff2"); font-weight: 200 800; }
@font-face { font-family: "Bricolage"; src: url("${pathToFileURL(join(fonts, "bricolage-grotesque/files/bricolage-grotesque-latin-ext-wght-normal.woff2")).href}") format("woff2"); font-weight: 200 800; unicode-range: U+0100-024F, U+1E00-1EFF, U+2020, U+20A0-20AB, U+20AD-20CF; }
@font-face { font-family: "Instrument"; src: url("${pathToFileURL(join(fonts, "instrument-sans/files/instrument-sans-latin-wght-normal.woff2")).href}") format("woff2"); font-weight: 400 700; }
@font-face { font-family: "Instrument"; src: url("${pathToFileURL(join(fonts, "instrument-sans/files/instrument-sans-latin-ext-wght-normal.woff2")).href}") format("woff2"); font-weight: 400 700; unicode-range: U+0100-024F, U+1E00-1EFF; }
@page { size: A4; margin: 18mm 18mm 20mm; }
:root { --ink: #14183a; --indigo: #151c57; --blue: #2b3ccf; --saffron: #f2b33d; --paper: #f4f5fa; --muted: #565c80; --line: #dcdff0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "Instrument", sans-serif; font-size: 10.5pt; line-height: 1.55; color: var(--ink); }
h1, h2, h3, h4 { font-family: "Bricolage", sans-serif; line-height: 1.15; color: var(--indigo); break-after: avoid; }
h2 { font-size: 19pt; font-weight: 750; margin: 11mm 0 4mm; }
/* Long sections start on a fresh page; short ones follow on. */
h2.new-page { break-before: page; margin-top: 0; }
h2::after { content: ""; display: block; width: 14mm; height: 1.2mm; margin-top: 2.5mm; border-radius: 1mm; background: var(--saffron); }
h3 { font-size: 13pt; font-weight: 700; margin: 7mm 0 2mm; }
h4 { font-size: 11pt; font-weight: 700; margin: 5mm 0 1.5mm; }
p { margin: 0 0 3mm; }
ul, ol { margin: 0 0 3.5mm; padding-left: 6mm; }
li { margin-bottom: 1.2mm; }
li::marker { color: var(--blue); font-weight: 700; }
strong { font-weight: 650; color: var(--indigo); }
a { color: var(--blue); text-decoration: none; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 5mm; font-size: 9.5pt; break-inside: avoid; }
th { font-family: "Bricolage", sans-serif; font-weight: 700; color: var(--indigo); text-align: center; padding: 2mm 1.5mm; border-bottom: 0.5mm solid var(--indigo); }
th:first-child, td:first-child { text-align: left; }
td { padding: 1.8mm 1.5mm; border-bottom: 0.25mm solid var(--line); text-align: center; }
td:not(:first-child) { color: var(--blue); font-weight: 700; }
tr:nth-child(even) td { background: #fafbfe; }
figure { margin: 4mm 0 6mm; break-inside: avoid; }
figure img { display: block; width: 100%; border: 0.3mm solid var(--line); border-radius: 2.5mm; box-shadow: 0 1mm 3mm rgba(21, 28, 87, 0.08); }
figcaption { margin-top: 1.8mm; font-size: 8.5pt; color: var(--muted); }

/* Cover */
.cover { height: 257mm; display: flex; flex-direction: column; justify-content: space-between; padding: 16mm 14mm; border-radius: 5mm; color: #fff;
  background-color: var(--indigo);
  background-image: radial-gradient(circle at 85% 12%, rgba(242, 179, 61, 0.22), transparent 38%),
    repeating-linear-gradient(45deg, rgba(255,255,255,0.045) 0 1px, transparent 1px 9mm),
    repeating-linear-gradient(-45deg, rgba(255,255,255,0.045) 0 1px, transparent 1px 9mm); }
.cover__mark { display: flex; align-items: center; gap: 3.5mm; font-family: "Bricolage", sans-serif; font-weight: 700; font-size: 12pt; line-height: 1.1; }
.cover__mark svg { width: 11mm; height: 11mm; }
.cover h1 { color: #fff; font-size: 40pt; font-weight: 800; margin: 0 0 6mm; letter-spacing: -0.02em; }
.cover__lede { font-size: 14pt; line-height: 1.4; max-width: 140mm; color: rgba(255,255,255,0.88); margin: 0 0 8mm; }
.cover__lede p { margin: 0; }
.cover__meta { display: flex; justify-content: space-between; align-items: flex-end; font-size: 9.5pt; color: rgba(255,255,255,0.7); }
.cover__bar { width: 30mm; height: 1.6mm; border-radius: 1mm; background: var(--saffron); margin-bottom: 6mm; }

/* Contents */
.toc h2 { break-before: page; }
.toc ol { list-style: none; padding: 0; counter-reset: s; columns: 1; }
.toc li { counter-increment: s; display: flex; gap: 4mm; align-items: baseline; padding: 2.4mm 0; border-bottom: 0.25mm solid var(--line); margin: 0; font-size: 11.5pt; }
.toc li::before { content: counter(s, decimal-leading-zero); font-family: "Bricolage", sans-serif; font-weight: 700; color: var(--saffron); min-width: 8mm; }
.toc a { color: var(--ink); }
</style>
</head>
<body>
<section class="cover">
  <div class="cover__mark">
    <svg viewBox="0 0 48 48" aria-hidden="true"><g fill="none" stroke="#fff" stroke-width="2.2"><rect x="10" y="10" width="28" height="28" rx="2"/><rect x="10" y="10" width="28" height="28" rx="2" transform="rotate(45 24 24)"/></g><circle cx="24" cy="24" r="3.4" fill="#f2b33d"/></svg>
    <span>Business Project<br>Assistance</span>
  </div>
  <div>
    <div class="cover__bar"></div>
    <h1>${guide.title}</h1>
    <div class="cover__lede">${intro}</div>
  </div>
  <div class="cover__meta"><span>${date}</span><span>${guide.lang === "fr" ? "Version française" : "English edition"}</span></div>
</section>
<section class="toc"><h2>${guide.contents}</h2><ol>${toc}</ol></section>
${rest}
</body>
</html>`;
}

function splitFirst(html) {
  const end = html.indexOf("</p>") + 4;
  return [html.slice(0, end), html.slice(end)];
}

const browser = await chromium.launch();
for (const guide of GUIDES) {
  const htmlPath = join(docs, `.user-guide-${guide.lang}.html`);
  writeFileSync(htmlPath, render(guide));
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: join(docs, guide.out),
    format: "A4",
    preferCSSPageSize: true,
    printBackground: true,
    outline: true,
    tagged: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: `<div style="width:100%;padding:0 18mm;font-family:sans-serif;font-size:7.5pt;color:#565c80;display:flex;justify-content:space-between"><span>${guide.footer}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  });
  await page.close();
  unlinkSync(htmlPath);
  console.log(`docs/${guide.out}`);
}
await browser.close();
