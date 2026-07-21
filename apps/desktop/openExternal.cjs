/**
 * 桌面壳外链打开：仅允许 http(s) 交给系统浏览器。
 */

/**
 * 判断 URL 是否允许用系统浏览器打开。
 * @param {string} url
 * @returns {boolean}
 */
function isAllowedExternalUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

module.exports = {
  isAllowedExternalUrl,
};
