/**
 * 桌面壳外链白名单单测。
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const { isAllowedExternalUrl } = require("./openExternal.cjs");

describe("isAllowedExternalUrl", () => {
  it("允许 http(s) GitHub 仓库地址", () => {
    assert.equal(
      isAllowedExternalUrl("https://github.com/GodyuFF/SuperVideoGenerator"),
      true,
    );
    assert.equal(isAllowedExternalUrl("http://example.com"), true);
  });

  it("拒绝非 http(s) 与非法 URL", () => {
    assert.equal(isAllowedExternalUrl("file:///etc/passwd"), false);
    assert.equal(isAllowedExternalUrl("javascript:alert(1)"), false);
    assert.equal(isAllowedExternalUrl(""), false);
    assert.equal(isAllowedExternalUrl("not a url"), false);
  });
});
