/** 测试替身：零网络、零真实时间、可脚本化。 */

import type {
  Assignment,
  Decision,
  Input,
  Ticket,
  Trigger,
} from "../src/domain.ts";
import type { AssessContext } from "../src/ports.ts";

export class ScriptedAssessor {
  private readonly decisions: Decision[];
  readonly calls: AssessContext[] = [];

  constructor(decisions: Decision[] = []) {
    this.decisions = [...decisions];
  }

  assess(context: AssessContext): Decision {
    this.calls.push(context);
    return (
      this.decisions.shift() ?? {
        kind: "ignore",
        strength: "inferred",
        reason: "script-exhausted",
        rules: [],
        scope: "ticket",
      }
    );
  }
}

export class RecordingExecutor {
  readonly launched: { assignment: Assignment; ticket: Ticket }[] = [];
  readonly delivered: { ticket: Ticket; input: Input }[] = [];
  readonly stopped: Assignment[] = [];
  failLaunch = false;

  launch(assignment: Assignment, ticket: Ticket): void {
    if (this.failLaunch) throw new Error("launch refused");
    this.launched.push({ assignment, ticket });
  }

  deliver(ticket: Ticket, input: Input): void {
    this.delivered.push({ ticket, input });
  }

  stop(assignment: Assignment): void {
    this.stopped.push(assignment);
  }
}

export class StaticSource {
  readonly name: string;
  private pending: Trigger[];

  constructor(name: string, triggers: Trigger[]) {
    this.name = name;
    this.pending = [...triggers];
  }

  poll(): Trigger[] {
    const batch = this.pending;
    this.pending = [];
    return batch;
  }
}