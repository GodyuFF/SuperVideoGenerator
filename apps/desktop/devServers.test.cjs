/**
 * devServers 纯函数单测（不真正拉起服务）。
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { resolveTooling, probeUrl, viteProbeUrls } = require("./devServers.cjs");

describe("devServers helpers", () => {
  it("resolveTooling 在仓库根下定位 python", () => {
    const repo = path.resolve(__dirname, "..", "..");
    const t = resolveTooling(repo);
    assert.ok(t.npm);
    assert.equal(typeof t.python, "string");
  });

  it("probeUrl 对拒绝连接返回 false", async () => {
    const ok = await probeUrl("http://127.0.0.1:1/", 400);
    assert.equal(ok, false);
  });

  it("viteProbeUrls 同时覆盖 localhost 与 127.0.0.1", () => {
    const urls = viteProbeUrls("http://localhost:5173");
    assert.ok(urls.includes("http://localhost:5173"));
    assert.ok(urls.includes("http://127.0.0.1:5173"));
  });
});
