/** AI 执行中禁用人工编辑时的提示条 */

export function ManualEditBanner({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <p className="manual-edit-banner" role="status">
      AI 执行中，资产与剧本内容暂不可手动编辑；执行完成后可继续操作。
    </p>
  );
}
