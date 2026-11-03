/** 时钟端口：所有时间来源必须经过这里，测试才能确定性。 */
export interface Clock {
    now(): number;
}
export declare class SystemClock implements Clock {
    now(): number;
}
export declare class FakeClock implements Clock {
    private current;
    constructor(start?: number);
    now(): number;
    advance(seconds: number): number;
}
