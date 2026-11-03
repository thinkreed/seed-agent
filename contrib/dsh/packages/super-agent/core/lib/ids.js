/** ID 工厂：运行期随机、测试确定性。 */
import { randomUUID } from "node:crypto";
export class SeqIds {
    counters = new Map();
    /** 用已有 ID 预热计数器，避免进程重启后与历史事件撞号。 */
    constructor(existing = []) {
        for (const id of existing) {
            const match = /^(.*)-(\d+)$/.exec(id);
            if (!match)
                continue;
            const prefix = match[1];
            const value = Number(match[2]);
            if (value > (this.counters.get(prefix) ?? 0))
                this.counters.set(prefix, value);
        }
    }
    next(prefix) {
        const value = (this.counters.get(prefix) ?? 0) + 1;
        this.counters.set(prefix, value);
        return `${prefix}-${String(value).padStart(6, "0")}`;
    }
}
export class UuidIds {
    next(prefix) {
        return `${prefix}-${randomUUID().replaceAll("-", "").slice(0, 10)}`;
    }
}
//# sourceMappingURL=ids.js.map