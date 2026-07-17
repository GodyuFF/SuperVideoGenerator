const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { resolveUserDataRoot } = require("./userDataPaths.cjs");

describe("resolveUserDataRoot", () => {
  it("Windows 使用 LOCALAPPDATA/SuperVideoGenerator", () => {
    const root = resolveUserDataRoot(
      {},
      "win32",
      "C:\\Users\\x",
      "C:\\Users\\x\\AppData\\Local",
    );
    assert.equal(
      root,
      path.join("C:\\Users\\x\\AppData\\Local", "SuperVideoGenerator"),
    );
  });

  it("macOS 使用 Application Support", () => {
    const root = resolveUserDataRoot({}, "darwin", "/Users/x", "");
    assert.equal(
      root,
      path.join("/Users/x", "Library", "Application Support", "SuperVideoGenerator"),
    );
  });
});
