/** 从模型输出里提取 JSON 对象：容忍 fenced code block 与前后散文。 */

export function extractJsonObject(raw: string): Record<string, unknown> | null {
  const text = raw.trim();
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(text);
  const candidates = [fenced?.[1] ?? "", text];
  for (const candidate of candidates) {
    const parsed = tryParse(candidate.trim());
    if (parsed) return parsed;
    const start = candidate.indexOf("{");
    const end = candidate.lastIndexOf("}");
    if (start >= 0 && end > start) {
      const inner = tryParse(candidate.slice(start, end + 1));
      if (inner) return inner;
    }
  }
  return null;
}

function tryParse(value: string): Record<string, unknown> | null {
  if (!value.startsWith("{")) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}