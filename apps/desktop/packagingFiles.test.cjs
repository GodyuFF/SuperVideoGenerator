/**
 * 校验 electron-builder 打包白名单覆盖主进程本地 require 依赖。
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/** 从源码中收集相对路径的 .cjs require。 */
function collectLocalCjsRequires(source) {
  const matches = source.matchAll(/require\(["']\.\/([^"']+\.cjs)["']\)/g);
  return [...new Set([...matches].map((m) => m[1]))];
}

/** 解析 electron-builder.yml 的 files 列表（仅本目录简单 YAML 行）。 */
function parseBuilderFilesList(ymlText) {
  const lines = ymlText.split(/\r?\n/);
  const files = [];
  let inFiles = false;
  for (const line of lines) {
    if (/^files:\s*$/.test(line)) {
      inFiles = true;
      continue;
    }
    if (inFiles) {
      const m = line.match(/^\s+-\s+(.+)\s*$/);
      if (m) {
        files.push(m[1].trim());
        continue;
      }
      if (/^\S/.test(line)) break;
    }
  }
  return files;
}

describe("electron-builder files 白名单", () => {
  it("包含 main.cjs 及其本地 .cjs 依赖（含传递）", () => {
    const root = __dirname;
    const yml = fs.readFileSync(path.join(root, "electron-builder.yml"), "utf8");
    const packaged = new Set(parseBuilderFilesList(yml));
    assert.ok(packaged.has("main.cjs"), "files 须包含 main.cjs");

    const queue = ["main.cjs"];
    const seen = new Set();
    while (queue.length) {
      const name = queue.shift();
      if (seen.has(name)) continue;
      seen.add(name);
      assert.ok(
        packaged.has(name),
        `打包白名单缺少 ${name}（主进程会 require 它）`,
      );
      const src = fs.readFileSync(path.join(root, name), "utf8");
      for (const dep of collectLocalCjsRequires(src)) {
        if (!seen.has(dep)) queue.push(dep);
      }
    }
  });
});
