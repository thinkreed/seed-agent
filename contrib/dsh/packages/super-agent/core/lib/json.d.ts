/** 从模型输出里提取 JSON 对象：容忍 fenced code block 与前后散文。 */
export declare function extractJsonObject(raw: string): Record<string, unknown> | null;
