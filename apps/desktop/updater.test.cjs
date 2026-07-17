const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const { mergeUpdateState, toCheckResult } = require("./updater.cjs");

describe("updater state helpers", () => {
  it("mergeUpdateState 保留未覆盖字段", () => {
    const prev = {
      status: "idle",
      currentVersion: "0.1.0",
      message: "ok",
    };
    const next = mergeUpdateState(prev, {
      status: "downloading",
      percent: 42,
    });
    assert.equal(next.currentVersion, "0.1.0");
    assert.equal(next.status, "downloading");
    assert.equal(next.percent, 42);
  });

  it("toCheckResult 映射 IPC 结构", () => {
    const result = toCheckResult({
      status: "downloaded",
      currentVersion: "0.1.0",
      version: "0.2.0",
      message: "ready",
      percent: 100,
    });
    assert.deepEqual(result, {
      status: "downloaded",
      version: "0.2.0",
      message: "ready",
    });
  });
});
