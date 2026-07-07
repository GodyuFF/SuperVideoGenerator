import type { A2UIComponent } from "../types";

/** 解析 select 初始值：与 options 对齐，避免 UI 显示首项但 state 为空。 */
export function resolveSelectValue(component: A2UIComponent): string {
  const options = component.options ?? [];
  if (options.length === 0) {
    return "";
  }
  const raw = component.value;
  const str = raw === undefined || raw === null ? "" : String(raw).trim();
  if (str && options.some((opt) => String(opt.value) === str)) {
    return str;
  }
  return String(options[0]?.value ?? "");
}

export function initialA2UIValues(
  components: A2UIComponent[]
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const c of components) {
    if (c.component === "checkbox") {
      values[c.id] = Boolean(c.value);
    } else if (c.component === "select") {
      values[c.id] = resolveSelectValue(c);
    } else if (c.component === "text") {
      const raw = c.value;
      values[c.id] = raw === undefined || raw === null ? "" : raw;
    }
  }
  return values;
}

export function isA2UIComponentValueMissing(
  component: A2UIComponent,
  value: unknown
): boolean {
  if (!component.required) {
    return false;
  }
  if (component.component === "checkbox") {
    return value !== true;
  }
  if (value === undefined || value === null) {
    return true;
  }
  return String(value).trim() === "";
}

export function missingRequiredComponents(
  components: A2UIComponent[],
  values: Record<string, unknown>
): A2UIComponent[] {
  return components.filter((c) =>
    isA2UIComponentValueMissing(c, values[c.id])
  );
}
