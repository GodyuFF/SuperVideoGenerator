/**
 * 桌面媒体路径解析单元测试（node:test）。
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");
const {
  parseMediaRelativePath,
  resolveLocalMediaPath,
  guessMime,
} = require("./mediaPath.cjs");

test("parseMediaRelativePath accepts API media URL path", () => {
  const rel = parseMediaRelativePath(
    "/api/projects/proj_a/scripts/script_b/assets/media/foo.png",
  );
  assert.equal(rel, "projects/proj_a/scripts/script_b/assets/media/foo.png");
});

test("parseMediaRelativePath accepts encoded filename", () => {
  const rel = parseMediaRelativePath(
    "/api/projects/p/scripts/s/assets/media/" + encodeURIComponent("a b.mp3"),
  );
  assert.equal(rel, "projects/p/scripts/s/assets/media/a b.mp3");
});

test("parseMediaRelativePath rejects traversal-looking unrelated paths", () => {
  assert.equal(parseMediaRelativePath("../secrets.txt"), null);
  assert.equal(parseMediaRelativePath("/etc/passwd"), null);
});

test("resolveLocalMediaPath stays inside data root", () => {
  const dataRoot = path.join(os.tmpdir(), "svf-desktop-test-data");
  const hit = resolveLocalMediaPath(
    "/api/projects/p1/scripts/s1/assets/media/x.png",
    dataRoot,
  );
  assert.ok(hit);
  assert.equal(hit.name, "x.png");
  assert.ok(hit.absolutePath.startsWith(path.resolve(dataRoot)));
});

test("resolveLocalMediaPath blocks escape via crafted segments", () => {
  const dataRoot = path.join(os.tmpdir(), "svf-desktop-test-data");
  // parse rejects non-matching patterns; double-check resolve null
  assert.equal(resolveLocalMediaPath("../../outside.png", dataRoot), null);
});

test("guessMime maps common types", () => {
  assert.equal(guessMime("a.PNG"), "image/png");
  assert.equal(guessMime("a.mp3"), "audio/mpeg");
  assert.equal(guessMime("a.mp4"), "video/mp4");
});
