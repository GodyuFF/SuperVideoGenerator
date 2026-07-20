import fs from "fs";
import path from "path";
import vm from "vm";
import { fileURLToPath } from "url";

const root = path.dirname(fileURLToPath(import.meta.url));
const mustFiles = [
  "index.html",
  "styles.css",
  "i18n.js",
  "assets/demo-final.mp4",
  "assets/edit-timeline.png",
  "assets/wechat-group-qr.png",
];
for (const f of mustFiles) {
  const p = path.join(root, f);
  if (!fs.existsSync(p)) {
    console.error("missing", f);
    process.exit(1);
  }
}

const code = fs.readFileSync(path.join(root, "i18n.js"), "utf8");
const ctx = {
  window: {},
  document: {
    documentElement: {},
    querySelectorAll: () => [],
    addEventListener: () => {},
  },
};
vm.runInNewContext(code + "\nthis.out = window.SvgSiteI18n;", ctx);
const keys = new Set(Object.keys(ctx.out.STRINGS.zh));
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const used = [...html.matchAll(/data-i18n="([^"]+)"/g)].map((m) => m[1]);
const missing = used.filter((k) => !keys.has(k));
if (missing.length) {
  console.error("i18n keys missing in dictionary:", missing);
  process.exit(1);
}
console.log("smoke ok", { files: mustFiles.length, i18nUsed: used.length });
