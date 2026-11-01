/** 时钟端口：所有时间来源必须经过这里，测试才能确定性。 */

export interface Clock {
  now(): number;
}

export class SystemClock implements Clock {
  now(): number {
    return Date.now() / 1000;
  }
}

export class FakeClock implements Clock {
  private current: number;

  constructor(start = 1_700_000_000) {
    this.current = start;
  }

  now(): number {
    return this.current;
  }

  advance(seconds: number): number {
    if (seconds < 0) throw new RangeError("clock cannot move backwards");
    this.current += seconds;
    return this.current;
  }
}