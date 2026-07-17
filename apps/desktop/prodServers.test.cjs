const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  resolveRuntimeRoot,
  resolveEmbeddedPython,
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
