/** ID 工厂：运行期随机、测试确定性。 */
export interface IdFactory {
    next(prefix: string): string;
}
export declare class SeqIds implements IdFactory {
    private counters;
    /** 用已有 ID 预热计数器，避免进程重启后与历史事件撞号。 */
    constructor(existing?: Iterable<string>);
    next(prefix: string): string;
}
export declare class UuidIds implements IdFactory {
    next(prefix: string): string;
}
