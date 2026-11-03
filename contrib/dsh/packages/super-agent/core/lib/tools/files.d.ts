/**
 * 文件工具：全部限定在工单目录内，路径逃逸直接拒绝。
 * 返回结构化结果，供模型作为 observation。
 */
import type { ReactTool } from "../react.ts";
export declare class PathEscapeError extends Error {
    constructor(requested: string);
}
export declare function resolveInside(root: string, requested: string): string;
export declare function fileTools(root: string): Record<string, ReactTool>;
export declare function workspacePath(root: string, ...parts: string[]): string;
