/** OpenCut Classic 动态加载模块声明（tsc 不深入 opencut 子树）。 */
declare module "./opencut/SvfClassicEditor" {
  import type { EditTimelineData } from "../edit/types";

  export function SvfClassicEditor(props: {
    projectId: string;
    scriptId: string;
    onSave: (timeline: EditTimelineData) => Promise<void>;
  }): JSX.Element;
}
