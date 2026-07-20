/** JSON Schema 展示辅助：解析 properties 为表格行。 */

export type JsonSchemaObject = Record<string, unknown>;

export interface SchemaFieldRow {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

/** 判断是否为普通对象。 */
function isRecord(value: unknown): value is JsonSchemaObject {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** 将 JSON Schema type 字段格式化为可读标签。 */
export function schemaTypeLabel(field: JsonSchemaObject): string {
  const typeValue = field.type;
  if (typeof typeValue === "string") return typeValue;
  if (Array.isArray(typeValue)) return typeValue.map(String).join(" | ");
  if (field.enum) return `enum(${field.enum.length})`;
  if (field.$ref) return String(field.$ref);
  if (field.anyOf || field.oneOf || field.allOf) return "union";
  if (field.items) return "array";
  if (field.properties) return "object";
  return "unknown";
}

/** 提取 schema 顶层 properties 为表格行。 */
export function flattenSchemaProperties(schema?: JsonSchemaObject | null): SchemaFieldRow[] {
  if (!schema || !isRecord(schema)) return [];
  const props = schema.properties;
  if (!isRecord(props)) return [];
  const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : []);
  return Object.entries(props).map(([name, raw]) => {
    const field = isRecord(raw) ? raw : {};
    const description = typeof field.description === "string" ? field.description : "";
    return {
      name,
      type: schemaTypeLabel(field),
      required: required.has(name),
      description,
    };
  });
}

/** 格式化 JSON Schema 为缩进字符串。 */
export function formatSchemaJson(schema?: JsonSchemaObject | null): string | null {
  if (!schema || !isRecord(schema)) return null;
  try {
    return JSON.stringify(schema, null, 2);
  } catch {
    return null;
  }
}
