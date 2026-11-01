/** ID 工厂：运行期随机、测试确定性。 */

import { randomUUID } from "node:crypto";

export interface IdFactory {
  next(prefix: string): string;
}

export class SeqIds implements IdFactory {
  private counters = new Map<string, number>();

  next(prefix: string): string {
    const value = (this.counters.get(prefix) ?? 0) + 1;
    this.counters.set(prefix, value);
    return `${prefix}-${String(value).padStart(6, "0")}`;
  }
}

export class UuidIds implements IdFactory {
  next(prefix: string): string {
    return `${prefix}-${randomUUID().replaceAll("-", "").slice(0, 10)}`;
  }
}