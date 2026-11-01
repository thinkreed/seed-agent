/**
 * 文件工具：全部限定在工单目录内，路径逃逸直接拒绝。
 * 返回结构化结果，供模型作为 observation。
 */

import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import type { ReactTool } from "../react.ts";

export class PathEscapeError extends Error {
  constructor(requested: string) {
    super(`path escapes workspace: ${requested}`);
    this.name = "PathEscapeError";
  }
}

const MAX_READ_BYTES = 200_000;

export function resolveInside(root: string, requested: string): string {
  const base = resolve(root);
  const target = resolve(base, requested);
  const rel = relative(base, target);
  if (rel.startsWith("..") || rel.includes(`..${require_sep()}`) || resolve(target) !== target) {
    throw new PathEscapeError(requested);
  }
  if (rel !== "" && !target.startsWith(base)) throw new PathEscapeError(requested);
  return target;
}

function require_sep(): string {
  return process.platform === "win32" ? "\\" : "/";
}

export function fileTools(root: string): Record<string, ReactTool> {
  return {
    read_file: {
      run: async (args) => {
        const path = resolveInside(root, String(args.path ?? ""));
        if (!existsSync(path)) return { error: `not found: ${String(args.path)}` };
        const stat = statSync(path);
        if (stat.isDirectory()) return { error: "is a directory; use list_files" };
        const text = readFileSync(path, "utf8");
        return {
          path: relative(root, path) || ".",
          bytes: stat.size,
          truncated: text.length > MAX_READ_BYTES,
          content: text.slice(0, MAX_READ_BYTES),
        };
      },
    },
    write_file: {
      run: async (args) => {
        const path = resolveInside(root, String(args.path ?? ""));
        const content = String(args.content ?? "");
        writeFileSync(path, content, "utf8");
        return { path: relative(root, path), bytes: Buffer.byteLength(content) };
      },
    },
    edit_file: {
      run: async (args) => {
        const path = resolveInside(root, String(args.path ?? ""));
        const oldText = String(args.old ?? "");
        const newText = String(args.new ?? "");
        if (!oldText) return { error: "old must not be empty" };
        if (!existsSync(path)) return { error: `not found: ${String(args.path)}` };
        const current = readFileSync(path, "utf8");
        const occurrences = current.split(oldText).length - 1;
        if (occurrences === 0) return { error: "old text not found" };
        if (occurrences > 1 && args.all !== true) {
          return { error: `old text appears ${occurrences} times; pass all=true to replace all` };
        }
        const next = args.all === true ? current.split(oldText).join(newText) : current.replace(oldText, newText);
        writeFileSync(path, next, "utf8");
        return { path: relative(root, path), replaced: occurrences };
      },
    },
    list_files: {
      run: async (args) => {
        const path = resolveInside(root, String(args.path ?? "."));
        if (!existsSync(path)) return { error: `not found: ${String(args.path ?? ".")}` };
        if (!statSync(path).isDirectory()) return { error: "not a directory" };
        return {
          path: relative(root, path) || ".",
          entries: readdirSync(path, { withFileTypes: true })
            .slice(0, 500)
            .map((entry) => (entry.isDirectory() ? `${entry.name}/` : entry.name))
            .sort(),
        };
      },
    },
  };
}

export function workspacePath(root: string, ...parts: string[]): string {
  return join(root, ...parts);
}