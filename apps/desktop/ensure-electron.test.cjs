/**
 * ensure-electron 纯函数单测（不联网）。
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const {
  readElectronVersion,
  buildDownloadUrl,
  resolveElectronExe,
  resolveInstallRoot,
} = require("./ensure-electron.cjs");

describe("ensure-electron helpers", () => {
  it("readElectronVersion 解析 package.json 版本", () => {
    const v = readElectronVersion();
    assert.match(v, /^\d+\.\d+\.\d+$/);
  });

  it("buildDownloadUrl 使用镜像与平台架构", () => {
    const prev = process.env.ELECTRON_MIRROR;
    process.env.ELECTRON_MIRROR = "https://example.test/electron/";
    try {
      const url = buildDownloadUrl("33.2.0");
      assert.equal(
        url,
        `https://example.test/electron/v33.2.0/electron-v33.2.0-${process.platform}-${process.arch}.zip`,
      );
    } finally {
      if (prev === undefined) delete process.env.ELECTRON_MIRROR;
      else process.env.ELECTRON_MIRROR = prev;
    }
  });

  it("resolveInstallRoot / resolveElectronExe 落在版本子目录", () => {
    const root = resolveInstallRoot("33.2.0");
    assert.match(root.replace(/\\/g, "/"), /electron\/v33\.2\.0$/);
    assert.equal(
      resolveElectronExe("33.2.0"),
      require("node:path").join(root, "electron.exe"),
    );
  });
});
