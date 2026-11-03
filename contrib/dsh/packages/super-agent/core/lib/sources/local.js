/** 本地 Source：把脚本/数组里的 Trigger 喂进系统（演示、回放、测试用）。 */
export class LocalSource {
    name;
    pending;
    batchSize;
    constructor(name, triggers, options = {}) {
        this.name = name;
        this.pending = [...triggers];
        this.batchSize = options.batchSize ?? Number.POSITIVE_INFINITY;
    }
    poll() {
        const batch = this.pending.slice(0, this.batchSize);
        this.pending = this.pending.slice(batch.length);
        return batch;
    }
    get remaining() {
        return this.pending.length;
    }
}
//# sourceMappingURL=local.js.map