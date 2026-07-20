/**
 * 从 icon.svg 栅格化为 Web/桌面品牌标 PNG 与 ICO（圆软小夜枭）。
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(ROOT, "apps/web/package.json"));
const sharp = require("sharp");

const SVG = path.join(ROOT, "apps/web/public/icon.svg");
const WEB = path.join(ROOT, "apps/web/public");
const DESKTOP = path.join(ROOT, "apps/desktop");
const ICO_SIZES = [16, 24, 32, 48, 64, 128, 256];

/** 将 SVG 渲染为指定边长的方正 PNG Buffer。 */
async function raster(size) {
  const input = fs.readFileSync(SVG);
  return sharp(input, { density: 384 })
    .resize(size, size, { fit: "fill" })
    .png()
    .toBuffer();
}

/** 构建含内嵌 PNG 的 ICO Buffer。 */
function icoFromPngs(sized) {
  const count = sized.length;
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(count, 4);

  const dir = Buffer.alloc(count * 16);
  const bodies = [];
  let offset = 6 + count * 16;

  sized.forEach(({ size, png }, i) => {
    const o = i * 16;
    dir[o] = size >= 256 ? 0 : size;
    dir[o + 1] = size >= 256 ? 0 : size;
    dir[o + 2] = 0;
    dir[o + 3] = 0;
    dir.writeUInt16LE(1, o + 4);
    dir.writeUInt16LE(32, o + 6);
    dir.writeUInt32LE(png.length, o + 8);
    dir.writeUInt32LE(offset, o + 12);
    bodies.push(png);
    offset += png.length;
  });

  return Buffer.concat([header, dir, ...bodies]);
}

/** 导出全部品牌标尺寸。 */
async function main() {
  if (!fs.existsSync(SVG)) {
    throw new Error(`missing source: ${SVG}`);
  }
  fs.mkdirSync(WEB, { recursive: true });
  fs.mkdirSync(DESKTOP, { recursive: true });

  const master = await raster(512);
  fs.writeFileSync(path.join(WEB, "icon.png"), master);
  fs.writeFileSync(path.join(DESKTOP, "icon.png"), master);
  fs.writeFileSync(path.join(DESKTOP, "icon-source.png"), master);

  for (const [size, name] of [
    [256, "icon-256.png"],
    [128, "icon-128.png"],
    [64, "icon-64.png"],
    [32, "favicon-32.png"],
  ]) {
    fs.writeFileSync(path.join(WEB, name), await raster(size));
  }

  const icoPngs = [];
  for (const size of ICO_SIZES) {
    icoPngs.push({ size, png: await raster(size) });
  }
  const ico = icoFromPngs(icoPngs);
  fs.writeFileSync(path.join(DESKTOP, "icon.ico"), ico);
  fs.writeFileSync(path.join(WEB, "icon.ico"), ico);

  console.log("ok", path.join(DESKTOP, "icon.ico"), ico.length, "sizes=", ICO_SIZES);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
