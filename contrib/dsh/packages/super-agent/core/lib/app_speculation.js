/** 内核 App 的投机执行接线：来源白名单、独立工作目录、只交付有价值结果。 */
import { Speculator } from "./speculation.js";
import { reactSpeculationRunner } from "./speculation_react.js";
export function buildAppSpeculation(options) {
    if (options.sources.length === 0)
        return undefined;
    const ticket = {
        id: "speculation",
        shortName: "spec",
        title: "静默投机尝试",
        mandate: {
            policyVersion: "speculation",
            strength: "explicit",
            scope: "speculation",
            source: "speculation",
            actor: "speculator",
            rules: [],
            triggerId: "speculation",
        },
        threadIds: [],
        channelIds: [],
        state: "open",
        stopped: false,
        createdAt: options.clock.now(),
    };
    const speculator = new Speculator({
        runner: reactSpeculationRunner({
            model: options.model,
            root: options.root,
            clock: options.clock,
            ticket,
        }),
        deliver: async (candidate, verdict) => {
            const address = candidate.channelIds?.[0];
            if (!address)
                return;
            await options.channels.send({ id: `spec-channel-${candidate.id}`, threadId: candidate.threadIds?.[0] ?? address, address }, `[投机执行] ${verdict.summary}`);
        },
        options: { sources: options.sources, maxConcurrent: 1, timeoutMs: 120_000 },
    });
    return { speculator, onTrigger: (trigger) => {
            if (!speculator.shouldRun(trigger))
                return;
            void speculator.run(trigger).catch(() => undefined);
        } };
}
//# sourceMappingURL=app_speculation.js.map