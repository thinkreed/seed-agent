/**
 * Shell 工具：在工单目录内执行命令。
 * 命令白名单/黑名单在配置里给，默认拦住明显危险的命令。
 */
import type { ReactTool } from "../react.ts";
export interface ShellToolOptions {
    readonly root: string;
    readonly timeoutMs?: number;
    readonly blocked?: readonly string[];
}
export declare function shellTool(options: ShellToolOptions): ReactTool;
