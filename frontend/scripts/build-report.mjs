// Builds the project report (French) from docs/rapport/rapport.md: docs/rapport/Rapport_BusinessProjectAssistance.pdf
// Run: npm run docs:report
// Diagrams: docs/rapport/diagrams/*.mmd are the Mermaid sources; the rendered *.svg next to them are inlined.
// Page numbers in the contents and the list of figures come from a first pass: Chromium writes every link target
// as a named destination, and we read which page each one landed on.
import { readFileSync, writeFileSync, unlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { marked } from "marked";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const dir = resolve(here, "../../docs/rapport");
const fonts = resolve(here, "../node_modules/@fontsource-variable");
const OUT = "Rapport_BusinessProjectAssistance.pdf";
const TITLE = "Business Project Assistance — Rapport de projet";

/** French typography: a non-breaking space before : ; ? ! and inside « » (text nodes only). */
const frenchSpacing = (html) =>
  html.replace(/>([^<]+)</g, (_, text) => `>${text.replace(/ ([:;?!»])/g, " $1").replace(/« /g, "« ")}<`);

const slug = (text) =>
  text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function render(pages = {}) {
  const markdown = readFileSync(join(dir, "rapport.md"), "utf8");
  const toc = [];
  const used = new Set();
  const uniqueId = (base) => {
    let id = base, n = 2;
    while (used.has(id)) id = `${base}-${n++}`;
    used.add(id);
    return id;
  };
  const renderer = new marked.Renderer();
  renderer.heading = ({ tokens, depth }) => {
    const text = marked.Parser.parseInline(tokens);
    const plain = text.replace(/<[^>]+>/g, "");
    const id = uniqueId(slug(plain));
    if (depth === 1) {
      toc.push({ id, text: plain, depth });
      const m = plain.match(/^Chapitre (\d+) : (.*)$/);
      if (m) {
        return `<h1 id="${id}" class="chapter"><span class="chapter__num">Chapitre ${m[1]}</span><span class="chapter__title">${m[2]}</span></h1>\n`;
      }
      return `<h1 id="${id}" class="part">${text}</h1>\n`;
    }
    if (depth === 2) toc.push({ id, text: plain, depth });
    return `<h${depth} id="${id}">${text}</h${depth}>\n`;
  };
  let html = marked.parse(markdown, { renderer });

  // Figures: number them, inline the diagrams (so they use the document's fonts), collect the list.
  const figures = [];
  html = html.replace(/<figure class="([^"]*)"( data-src="([^"]+)")?>([\s\S]*?)<figcaption>([\s\S]*?)<\/figcaption><\/figure>/g,
    (_, cls, __, src, inner, caption) => {
      const n = figures.length + 1;
      const id = `figure-${n}`;
      figures.push({ id, n, caption: caption.replace(/<[^>]+>/g, "") });
      let body = inner;
      if (src) {
        body = readFileSync(join(dir, src), "utf8")
          .replace(/<svg([^>]*?) style="max-width:[^"]*"/, "<svg$1")
          .replace(/<svg /, '<svg class="diagram__svg" ');
      }
      return `<figure id="${id}" class="${cls}">${body}<figcaption><span class="figure__num">Figure ${n}</span>${caption}</figcaption></figure>`;
    });

  // Placeholders left for the author stand out on screen and in print.
  html = html.replace(/\[À compléter([^\]]*)\]/g, '<span class="todo">[À compléter$1]</span>');
  html = frenchSpacing(html);

  const page = (id) => (pages[id] ? `<span class="toc__page">${pages[id]}</span>` : "");
  const tocHtml = toc
    .map((e) => `<li class="toc__l${e.depth}"><a href="#${e.id}">${e.text}</a>${page(e.id)}</li>`)
    .join("");
  const figHtml = figures
    .map((f) => `<li><a href="#${f.id}"><span class="figure__num">Figure ${f.n}</span>${f.caption}</a>${page(f.id)}</li>`)
    .join("");
  const font = (p) => pathToFileURL(join(fonts, p)).href;

  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>${TITLE}</title>
<base href="${pathToFileURL(dir + "/").href}">
<style>
@font-face { font-family: "Bricolage"; src: url("${font("bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2")}") format("woff2"); font-weight: 200 800; }
@font-face { font-family: "Bricolage"; src: url("${font("bricolage-grotesque/files/bricolage-grotesque-latin-ext-wght-normal.woff2")}") format("woff2"); font-weight: 200 800; unicode-range: U+0100-024F, U+1E00-1EFF, U+2020, U+20A0-20AB, U+20AD-20CF; }
@font-face { font-family: "Instrument"; src: url("${font("instrument-sans/files/instrument-sans-latin-wght-normal.woff2")}") format("woff2"); font-weight: 400 700; }
@font-face { font-family: "Instrument"; src: url("${font("instrument-sans/files/instrument-sans-latin-ext-wght-normal.woff2")}") format("woff2"); font-weight: 400 700; unicode-range: U+0100-024F, U+1E00-1EFF; }
@page { size: A4; margin: 20mm 16mm 20mm; }
:root { --ink: #14183a; --indigo: #151c57; --blue: #2b3ccf; --saffron: #f2b33d; --paper: #f4f5fa; --muted: #565c80; --line: #dcdff0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "Instrument", sans-serif; font-size: 10.5pt; line-height: 1.58; color: var(--ink); text-align: justify; hyphens: auto; }
h1, h2, h3, h4 { font-family: "Bricolage", sans-serif; line-height: 1.15; color: var(--indigo); break-after: avoid; text-align: left; hyphens: manual; }

/* Front matter and back matter titles, and chapters: each starts a page. */
h1.part { break-before: page; font-size: 24pt; font-weight: 780; margin: 0 0 7mm; letter-spacing: -0.01em; }
h1.part::after, h1.chapter .chapter__title::after { content: ""; display: block; width: 16mm; height: 1.3mm; margin-top: 3mm; border-radius: 1mm; background: var(--saffron); }
h1.chapter { break-before: page; margin: 0 0 9mm; padding: 9mm 0 0; border-top: 0.6mm solid var(--indigo); }
.chapter__num { display: block; font-size: 11pt; font-weight: 700; color: var(--blue); margin-bottom: 3mm; letter-spacing: 0.01em; }
.chapter__title { display: block; font-size: 25pt; font-weight: 780; letter-spacing: -0.01em; }
h2 { font-size: 15.5pt; font-weight: 740; margin: 9mm 0 3mm; }
h3 { font-size: 12pt; font-weight: 700; margin: 6mm 0 2mm; color: var(--blue); }
h4 { font-size: 10.5pt; font-weight: 700; margin: 4mm 0 1.5mm; }
p { margin: 0 0 3mm; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 3.5mm; padding-left: 6mm; text-align: left; }
li { margin-bottom: 1.2mm; }
li::marker { color: var(--blue); font-weight: 700; }
strong { font-weight: 650; color: var(--indigo); }
em { color: var(--muted); }
a { color: var(--blue); text-decoration: none; }
code { font-family: "Cascadia Mono", Consolas, monospace; font-size: 8.8pt; background: var(--paper); border: 0.2mm solid var(--line); border-radius: 1mm; padding: 0.2mm 1mm; color: var(--indigo); white-space: nowrap; }
.todo { color: #9a6a00; background: #fdf3dd; border-radius: 1mm; padding: 0.3mm 1.2mm; font-style: italic; }

table { width: 100%; border-collapse: collapse; margin: 2mm 0 5mm; font-size: 9.2pt; text-align: left; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { font-family: "Bricolage", sans-serif; font-weight: 700; color: #fff; background: var(--indigo); padding: 2mm 2mm; vertical-align: bottom; }
th:first-child { border-top-left-radius: 1.5mm; }
th:last-child { border-top-right-radius: 1.5mm; }
td { padding: 1.7mm 2mm; border-bottom: 0.25mm solid var(--line); vertical-align: top; }
tr:nth-child(even) td { background: #f8f9fd; }
.matrix { break-inside: avoid; }
.matrix td:not(:first-child), .matrix th:not(:first-child) { text-align: center; width: 15%; }
.matrix td:not(:first-child) { color: var(--blue); font-weight: 700; font-size: 11pt; }

figure { margin: 4mm 0 6mm; break-inside: avoid; text-align: center; }
figure.diagram { padding: 4mm; background: #fff; border: 0.3mm solid var(--line); border-radius: 2.5mm; }
.diagram__svg { display: block; width: 100%; height: auto; max-height: 205mm; margin: 0 auto; }
figure.diagram--narrow .diagram__svg { max-height: 175mm; }
/* Wide diagrams get the full width (Chromium clips anything in the page margins); tall ones nearly a full page. */
figure.diagram--wide { padding: 1.5mm; }
figure.diagram--tall .diagram__svg { max-height: 222mm; }
figure.shot img { display: block; width: 100%; border: 0.3mm solid var(--line); border-radius: 2.5mm; box-shadow: 0 1mm 3mm rgba(21, 28, 87, 0.08); }
figure.shot--narrow img { width: 78%; margin: 0 auto; }
figcaption { margin-top: 2.2mm; font-size: 8.8pt; color: var(--muted); text-align: center; }
.figure__num { font-weight: 700; color: var(--indigo); margin-right: 1.6mm; }
.figure__num::after { content: " —"; font-weight: 400; color: var(--muted); }

/* Cover */
.cover { height: 257mm; display: flex; flex-direction: column; justify-content: space-between; padding: 15mm 14mm 13mm; border-radius: 5mm; color: #fff; text-align: left;
  background-color: var(--indigo); position: relative; overflow: hidden; }
.cover > * { position: relative; }
.cover__pattern { position: absolute !important; inset: 0; width: 100%; height: 100%; }
.cover__top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8mm; }
.cover__mark { display: flex; align-items: center; gap: 3.5mm; font-family: "Bricolage", sans-serif; font-weight: 700; font-size: 12pt; line-height: 1.1; }
.cover__mark svg { width: 11mm; height: 11mm; }
.cover__school { text-align: right; font-size: 9.5pt; color: rgba(255,255,255,0.75); line-height: 1.5; }
.cover__school strong { color: #fff; font-family: "Bricolage", sans-serif; font-size: 11pt; }
.cover__kicker { font-family: "Bricolage", sans-serif; font-size: 11pt; font-weight: 600; color: var(--saffron); margin: 0 0 4mm; }
.cover h1 { color: #fff; font-size: 30pt; font-weight: 800; line-height: 1.08; margin: 0 0 5mm; letter-spacing: -0.02em; max-width: 160mm; }
.cover__en { font-size: 12.5pt; font-style: italic; color: rgba(255,255,255,0.8); margin: 0 0 9mm; max-width: 150mm; }
.cover__bar { width: 30mm; height: 1.6mm; border-radius: 1mm; background: var(--saffron); margin-bottom: 7mm; }
.cover__fields { display: grid; grid-template-columns: 46mm 1fr; gap: 2.4mm 6mm; font-size: 10pt; max-width: 150mm; padding: 6mm 7mm; border-radius: 3mm; background: #1d2569; border: 0.3mm solid #343d86; }
.cover__fields dt { color: rgba(255,255,255,0.62); }
.cover__fields dd { margin: 0; color: #fff; border-bottom: 0.3mm dotted rgba(255,255,255,0.35); min-height: 5mm; }
.cover__meta { display: flex; justify-content: space-between; align-items: flex-end; font-size: 9.5pt; color: rgba(255,255,255,0.7); }

/* Contents and list of figures */
.toc h1, .figures h1 { break-before: page; font-size: 24pt; font-weight: 780; margin: 0 0 6mm; }
.toc h1::after, .figures h1::after { content: ""; display: block; width: 16mm; height: 1.3mm; margin-top: 3mm; border-radius: 1mm; background: var(--saffron); }
.toc ol, .figures ol { list-style: none; padding: 0; margin: 0; text-align: left; }
.toc li, .figures li { display: flex; align-items: baseline; gap: 2mm; margin: 0; }
.toc li a, .figures li a { color: var(--ink); flex: 1; display: flex; align-items: baseline; }
.toc li a::after, .figures li a::after { content: ""; flex: 1; border-bottom: 0.3mm dotted #b9bdd8; margin: 0 2mm; transform: translateY(-1mm); }
.toc__l1 { padding: 2.6mm 0 1mm; font-family: "Bricolage", sans-serif; font-weight: 700; font-size: 11.5pt; }
.toc__l1 a { color: var(--indigo) !important; }
.toc__l2 { padding: 0.8mm 0 0.8mm 6mm; font-size: 9.8pt; }
.figures li { padding: 1.1mm 0; font-size: 9.8pt; }
.toc__page { font-variant-numeric: tabular-nums; color: var(--muted); min-width: 7mm; text-align: right; }
</style>
</head>
<body>
<section class="cover">
  <svg class="cover__pattern" aria-hidden="true" preserveAspectRatio="xMidYMid slice" viewBox="0 0 180 257">
    <defs>
      <pattern id="zellij" width="24" height="24" patternUnits="userSpaceOnUse">
        <g fill="none" stroke="#202873" stroke-width="0.45"><rect x="6" y="6" width="12" height="12"/><rect x="6" y="6" width="12" height="12" transform="rotate(45 12 12)"/></g>
      </pattern>
    </defs>
    <rect width="180" height="257" fill="url(#zellij)"/>
    <circle cx="165" cy="18" r="34" fill="#232c7d"/>
    <circle cx="165" cy="18" r="20" fill="#2b3591"/>
    <rect x="0" y="236" width="180" height="21" fill="#1a2266"/>
  </svg>
  <div class="cover__top">
    <div class="cover__mark">
      <svg viewBox="0 0 48 48" aria-hidden="true"><g fill="none" stroke="#fff" stroke-width="2.2"><rect x="10" y="10" width="28" height="28" rx="2"/><rect x="10" y="10" width="28" height="28" rx="2" transform="rotate(45 24 24)"/></g><circle cx="24" cy="24" r="3.4" fill="#f2b33d"/></svg>
      <span>Business Project<br>Assistance</span>
    </div>
    <div class="cover__school"><strong>Établissement / Institut</strong><br>[À compléter]</div>
  </div>
  <div>
    <div class="cover__bar"></div>
    <p class="cover__kicker">Rapport de projet de fin d'études</p>
    <h1>Conception et développement d'une application web de gestion de projets assistée par l'IA</h1>
    <p class="cover__en">Design and development of an AI-assisted project management web application</p>
    <dl class="cover__fields">
      <dt>Filière</dt><dd>&nbsp;</dd>
      <dt>Organisme d'accueil</dt><dd>&nbsp;</dd>
      <dt>Présenté par</dt><dd>&nbsp;</dd>
      <dt>Encadré par</dt><dd>&nbsp;</dd>
      <dt>Promotion</dt><dd>&nbsp;</dd>
    </dl>
  </div>
  <div class="cover__meta"><span>Business Project Assistance</span><span>${new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" }).format(new Date())}</span></div>
</section>
<section class="toc"><h1>Table des matières</h1><ol><li class="toc__l1"><a href="#liste-des-figures">Liste des figures</a>${page("liste-des-figures")}</li>${tocHtml}</ol></section>
<section class="figures"><h1 id="liste-des-figures">Liste des figures</h1><ol>${figHtml}</ol></section>
${html}
</body>
</html>`;
}

/** Page (1-based) of every named destination in a Chromium PDF (uncompressed object syntax, /Dests dictionary). */
function destinationPages(pdf) {
  const text = pdf.toString("latin1");
  const body = (id) => {
    const at = text.indexOf(`\n${id} 0 obj`);
    return at < 0 ? "" : text.slice(at, text.indexOf("endobj", at));
  };
  const catalog = text.match(/\/Type \/Catalog[\s\S]*?endobj/)?.[0] ?? "";
  const pagesRoot = catalog.match(/\/Pages (\d+) 0 R/)?.[1];
  const destsId = catalog.match(/\/Dests (\d+) 0 R/)?.[1];
  if (!pagesRoot || !destsId) return {};
  const order = [];
  const walk = (id) => {
    const b = body(id);
    if (/\/Type \/Page[^s]/.test(b)) return void order.push(id);
    for (const k of (b.match(/\/Kids \[([^\]]*)\]/)?.[1] ?? "").matchAll(/(\d+) 0 R/g)) walk(k[1]);
  };
  walk(pagesRoot);
  const pageOf = new Map(order.map((id, i) => [id, i + 1]));
  const result = {};
  for (const m of body(destsId).matchAll(/\/([^\s\[\]/<>()]+)\s*\[(\d+) 0 R \/XYZ/g)) {
    const name = m[1].replace(/#([0-9a-fA-F]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
    if (pageOf.has(m[2])) result[name] = pageOf.get(m[2]);
  }
  return result;
}

async function print(browser, html, path) {
  const htmlPath = join(dir, ".rapport.html");
  writeFileSync(htmlPath, html);
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  const pdf = await page.pdf({
    path,
    format: "A4",
    preferCSSPageSize: true,
    printBackground: true,
    outline: true,
    tagged: true,
    displayHeaderFooter: true,
    headerTemplate: `<div style="width:100%;padding:0 16mm;font-family:sans-serif;font-size:7.5pt;color:#8a8fb0;text-align:right">${TITLE}</div>`,
    footerTemplate: `<div style="width:100%;padding:0 16mm;font-family:sans-serif;font-size:8pt;color:#565c80;text-align:center"><span class="pageNumber"></span></div>`,
  });
  await page.close();
  unlinkSync(htmlPath);
  return pdf;
}

const browser = await chromium.launch();
const out = join(dir, OUT);
const first = await print(browser, render(), out);
const pages = destinationPages(first);
const found = Object.keys(pages).length;
await print(browser, render(pages), out);
await browser.close();
console.log(`docs/rapport/${OUT}${found ? "" : " (page numbers not found: contents printed without them)"}`);
