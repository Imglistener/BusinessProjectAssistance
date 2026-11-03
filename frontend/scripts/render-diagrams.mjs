// Renders docs/rapport/diagrams/*.mmd to SVG with Mermaid, in the report's fonts and colours (cas-utilisation.svg is drawn by hand).
// Mermaid is not a project dependency: run once `npm install --no-save mermaid@11`, then
// `node scripts/render-diagrams.mjs ../docs/rapport/diagrams node_modules/@fontsource-variable` from frontend/,
// then `npm run docs:report`.
import { readdirSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const [dir, fonts] = process.argv.slice(2);
const font = (p) => pathToFileURL(join(fonts, p)).href;

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@font-face { font-family: "Instrument"; src: url("${font("instrument-sans/files/instrument-sans-latin-wght-normal.woff2")}") format("woff2"); font-weight: 400 700; }
@font-face { font-family: "Instrument"; src: url("${font("instrument-sans/files/instrument-sans-latin-ext-wght-normal.woff2")}") format("woff2"); font-weight: 400 700; unicode-range: U+0100-024F, U+1E00-1EFF; }
body { font-family: "Instrument", sans-serif; }
</style></head><body><div id="probe" style="font-family: Instrument">Éé</div></body></html>`;

const b = await chromium.launch();
const page = await b.newPage();
const htmlPath = join(tmpdir(), "bpa-render-diagrams.html");
writeFileSync(htmlPath, html);
page.on("console", (m) => { if (m.type() === "error") console.log("page error:", m.text().slice(0, 200)); });
page.on("pageerror", (e) => console.log("pageerror:", e.message.slice(0, 200)));
await page.goto(pathToFileURL(htmlPath).href);
await page.evaluate(() => document.fonts.ready);
await page.addScriptTag({ path: resolve("node_modules/mermaid/dist/mermaid.min.js") });
await page.addScriptTag({ content: `
  window.mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    securityLevel: "loose",
    fontFamily: "Instrument, sans-serif",
    htmlLabels: false,
    flowchart: { htmlLabels: false, curve: "basis", padding: 10, nodeSpacing: 26, rankSpacing: 36, diagramPadding: 6 },
    sequence: { actorFontFamily: "Instrument", messageFontFamily: "Instrument", noteFontFamily: "Instrument", actorFontSize: 18, messageFontSize: 18, noteFontSize: 16, mirrorActors: false, width: 136, actorMargin: 18, boxMargin: 6, messageMargin: 30, diagramMarginX: 8, diagramMarginY: 8 },
    class: { htmlLabels: false, padding: 6 },
    state: { padding: 6 },
    themeVariables: {
      fontFamily: "Instrument, sans-serif",
      fontSize: "18px",
      primaryColor: "#eef0fb",
      primaryBorderColor: "#2b3ccf",
      primaryTextColor: "#14183a",
      secondaryColor: "#fdf3dd",
      tertiaryColor: "#f7f8fc",
      lineColor: "#565c80",
      textColor: "#14183a",
      clusterBkg: "#f7f8fc",
      clusterBorder: "#c9cde6",
      edgeLabelBackground: "#ffffff",
      noteBkgColor: "#fdf3dd",
      noteBorderColor: "#f2b33d",
      noteTextColor: "#14183a",
      actorBkg: "#151c57",
      actorBorder: "#151c57",
      actorTextColor: "#ffffff",
      actorLineColor: "#9aa0c8",
      signalColor: "#14183a",
      signalTextColor: "#14183a",
      labelBoxBkgColor: "#fdf3dd",
      labelBoxBorderColor: "#f2b33d",
      labelTextColor: "#14183a",
      loopTextColor: "#14183a",
      activationBkgColor: "#eef0fb",
      activationBorderColor: "#2b3ccf",
      sequenceNumberColor: "#ffffff",
    },
  });
    window.renderMermaid = async (id, text) => (await window.mermaid.render(id, text)).svg;
`});
await page.waitForFunction(() => typeof window.renderMermaid === "function");

for (const file of readdirSync(dir).filter((f) => f.endsWith(".mmd")).sort()) {
  const id = "d-" + file.replace(/\.mmd$/, "");
  try {
    const svg = await page.evaluate(([i, t]) => window.renderMermaid(i, t), [id, readFileSync(join(dir, file), "utf8")]);
    writeFileSync(join(dir, file.replace(/\.mmd$/, ".svg")), svg);
    console.log("ok  ", file);
  } catch (e) {
    console.log("FAIL", file, String(e).slice(0, 300));
  }
}
await b.close();
unlinkSync(htmlPath);
