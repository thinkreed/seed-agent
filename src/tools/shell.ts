/**
 * Shell 工具：在工单目录内执行命令。
 * 命令白名单/黑名单在配置里给，默认拦住明显危险的命令。
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import type { ReactTool } from "../react.ts";

const execFileAsync = promisify(execFile);

const DEFAULT_BLOCKED = ["rm", "rmdir", "del", "format", "shutdown", "reboot", "reg", "diskpart"];
const MAX_OUTPUT_BYTES = 60_000;

export interface ShellToolOptions {
  readonly root: string;
  readonly timeoutMs?: number;
  readonly blocked?: readonly string[];
}

export function shellTool(options: ShellToolOptions): ReactTool {
  return {
    run: async (args) => {
      const command = String(args.command ?? "").trim();
      if (!command) return { error: "empty command" };
      const first = command.split(/\s+/)[0] ?? "";
      const blocked = options.blocked ?? DEFAULT_BLOCKED;
      if (blocked.includes(first.toLowerCase())) return { error: `blocked command: ${first}` };
      try {
        const { stdout, stderr } = await execFileAsync(shellFile(), shellArgs(command), {
          cwd: options.root,
          timeout: options.timeoutMs ?? 120_000,
          maxBuffer: 4 * 1024 * 1024,
          windowsHide: true,
        });
        return { exitCode: 0, stdout: tail(stdout), stderr: tail(stderr), command };
      } catch (error) {
        const failed = error as { code?: number; stdout?: string; stderr?: string; message?: string };
        return {
          exitCode: typeof failed.code === "number" ? failed.code : -1,
          stdout: tail(failed.stdout ?? ""),
          stderr: tail(failed.stderr ?? failed.message ?? String(error)),
          command,
        };
      }
    },
  };
}

function shellFile(): string {
  return process.platform === "win32" ? "powershell.exe" : "/bin/sh";
}

function shellArgs(command: string): string[] {
  return process.platform === "win32"
    ? ["-NoProfile", "-NonInteractive", "-Command", command]
    : ["-c", command];
}

function tail(text: string): string {
  return text.length <= MAX_OUTPUT_BYTES ? text : `…${text.slice(text.length - MAX_OUTPUT_BYTES)}`;
}