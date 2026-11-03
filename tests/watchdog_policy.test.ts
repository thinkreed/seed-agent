import assert from "node:assert/strict";
import { test } from "node:test";

import { WatchdogController } from "../src/control.ts";
import type { Policy } from "../src/domain.ts";
import * as h from "./helpers.ts";

test("Watchdog 的 verdict 携带 policy 时自动 applyPolicy", () => {
  const policies: Policy[] = [];
  let retries = 0;
  const controller = new WatchdogController({
    retry: () => {
      retries += 1;
      return [];
    },
    setPolicy: (policy) => {
      policies.push(policy);
      return [];
    },
  });
  const outcome = controller.apply({
    findings: [{ kind: "stalled", ticketId: "tk-1", detail: "stalled" }],
    verdict: { action: "intervene", reason: "adjust policy", policy: h.policy() },
  });
  assert.equal(outcome.policyApplied, true);
  assert.equal(policies.length, 1);
  assert.equal(retries, 1);
});