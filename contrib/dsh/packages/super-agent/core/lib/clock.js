/** 时钟端口：所有时间来源必须经过这里，测试才能确定性。 */
export class SystemClock {
    now() {
        return Date.now() / 1000;
    }
}
export class FakeClock {
    current;
    constructor(start = 1_700_000_000) {
        this.current = start;
    }
    now() {
        return this.current;
    }
    advance(seconds) {
        if (seconds < 0)
            throw new RangeError("clock cannot move backwards");
        this.current += seconds;
        return this.current;
    }
}
//# sourceMappingURL=clock.js.map