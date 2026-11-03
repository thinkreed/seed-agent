/** 本地 Source：把脚本/数组里的 Trigger 喂进系统（演示、回放、测试用）。 */
import type { Trigger } from "../domain.ts";
import type { Source } from "../ports.ts";
export interface LocalSourceOptions {
    /** 每次 poll 最多返回多少条，用于验证批处理。 */
    readonly batchSize?: number;
}
export declare class LocalSource implements Source {
    readonly name: string;
    private pending;
    private readonly batchSize;
    constructor(name: string, triggers: readonly Trigger[], options?: LocalSourceOptions);
    poll(): Trigger[];
    get remaining(): number;
}
