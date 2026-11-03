/** JSONL 收件箱 Source：每行一个 Trigger，文件追加即产生事件（本地/CI 验证用）。 */
import type { Trigger } from "../domain.ts";
import type { Source } from "../ports.ts";
export declare class JsonlInboxSource implements Source {
    readonly name = "local";
    private readonly path;
    constructor(path: string);
    poll(): Promise<Trigger[]>;
}
