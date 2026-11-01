/** 本地 Source：把脚本/数组里的 Trigger 喂进系统（演示、回放、测试用）。 */

import type { Trigger } from "../domain.ts";
import type { Source } from "../ports.ts";

export interface LocalSourceOptions {
  /** 每次 poll 最多返回多少条，用于验证批处理。 */
  readonly batchSize?: number;
}

export class LocalSource implements Source {
  readonly name: string;
  private pending: Trigger[];
  private readonly batchSize: number;

  constructor(name: string, triggers: readonly Trigger[], options: LocalSourceOptions = {}) {
    this.name = name;
    this.pending = [...triggers];
    this.batchSize = options.batchSize ?? Number.POSITIVE_INFINITY;
  }

  poll(): Trigger[] {
    const batch = this.pending.slice(0, this.batchSize);
    this.pending = this.pending.slice(batch.length);
    return batch;
  }

  get remaining(): number {
    return this.pending.length;
  }
}