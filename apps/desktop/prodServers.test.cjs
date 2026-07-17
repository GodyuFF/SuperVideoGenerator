const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  resolveRuntimeRoot,
  resolveEmbeddedPython,
  isHealthStatusOk,
  isHealthBodyOk,
} = require("./prodServers.cjs");

describe("prodServers paths", () => {
  it("runtime 在 resources/runtime", () => {
    assert.equal(
      resolveRuntimeRoot("/app/resources"),
      path.join("/app/resources", "runtime"),
    );
  });

  it("Win python 路径", () => {
    const p = resolveEmbeddedPython(path.join("R", "runtime"), "win32");
    assert.ok(p.endsWith(path.join("python", "python.exe")));
  });
});

describe("prodServers health probe", () => {
  it("2xx 视为健康", () => {
    assert.equal(isHealthStatusOk(200), true);
    assert.equal(isHealthStatusOk(204), true);
  });

  it("非 2xx 视为不健康", () => {
    assert.equal(isHealthStatusOk(404), false);
    assert.equal(isHealthStatusOk(500), false);
    assert.equal(isHealthStatusOk(undefined), false);
  });

  it("body 含 status ok 视为有效", () => {
    assert.equal(isHealthBodyOk('{"status":"ok"}'), true);
    assert.equal(isHealthBodyOk('{"status": "ok", "version": 1}'), true);
    assert.equal(isHealthBodyOk('{"status":"fail"}'), false);
  });
});
