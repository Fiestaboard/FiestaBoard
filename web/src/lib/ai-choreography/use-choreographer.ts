"use client";

// Sequences the walkthrough of a turn.
//
// One job per tool call, played strictly in order: narrate(A) → wait for
// A's result → settle(A) → narrate(B) → … A result that lands while its
// narration is still playing switches the narration to fast; Stop (or a
// fatal error) aborts the current job between steps, runs its `stop`
// steps so nothing staged is left behind, and drops the rest. A draft —
// the block the model is still writing — starts a job before the call
// exists, so the screen is already moving when the call completes.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ToolCall, ToolResult } from "@/lib/ai-chat-types";

import { parseToolDraft } from "./draft";
import { ChoreographyAborted, runSteps } from "./engine";
import { getScript } from "./registry";
import type { ChoreographyContext, ChoreographyScript, Step } from "./types";

interface Job {
  id: string;
  name: string;
  script: ChoreographyScript;
  call: ToolCall | null;
  /** Shared with the script's draft/narrate so it can type only what is new. */
  progress: Record<string, unknown>;
  /** Batches of steps still to play, in order. */
  pending: Step[][];
  result?: ToolResult;
  /** Resolves the wait for the result or for more steps. */
  wake?: () => void;
  /** A draft job waits for its call; a call job waits for its result. */
  awaits: "call" | "result";
}

export interface Choreographer {
  /** A `tool_streaming` frame: the model is still writing this call. */
  onDraft(text: string): void;
  onToolCall(call: ToolCall): void;
  onToolResult(result: ToolResult): void;
  /** The server paused on a destructive call; show Approve/Deny at its anchor. */
  onAwaitingApproval(call: ToolCall): void;
  /** Stop or a fatal error: abort everything, leave nothing staged. */
  onAbort(): void;
  /** The turn ended without another call: a dangling draft is dropped. */
  onTurnEnd(): void;
  /** True while a walkthrough is on screen. */
  driving: boolean;
}

export function useChoreographer(ctx: ChoreographyContext): Choreographer {
  const ctxRef = useRef(ctx);
  useEffect(() => {
    ctxRef.current = ctx;
  }, [ctx]);

  const jobsRef = useRef<Job[]>([]);
  const runningRef = useRef<Job | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [driving, setDriving] = useState(false);

  const pump = useCallback(() => {
    if (runningRef.current) return;
    const job = jobsRef.current.shift();
    if (!job) {
      setDriving(false);
      return;
    }
    runningRef.current = job;
    setDriving(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const opts = { signal: controller.signal, isFast: () => job.result !== undefined };

    const play = async () => {
      try {
        // Drain narration; keep waiting (for more steps, the call, or the
        // result) until the job has both a call and a result.
        for (;;) {
          while (job.pending.length > 0) {
            const batch = job.pending.shift()!;
            await runSteps(batch, ctxRef.current, opts);
          }
          if (job.call && job.result !== undefined) break;
          if (controller.signal.aborted) throw new ChoreographyAborted();
          await new Promise<void>((resolve) => {
            job.wake = resolve;
            controller.signal.addEventListener("abort", () => resolve(), { once: true });
          });
          job.wake = undefined;
          if (controller.signal.aborted) throw new ChoreographyAborted();
        }
        const { call, result, script } = job;
        const ending =
          result.status === "ok"
            ? script.settle(call!, result, ctxRef.current)
            : (script.fail?.(call!, result, ctxRef.current) ?? script.settle(call!, result, ctxRef.current));
        await runSteps(ending, ctxRef.current, opts);
      } catch (err) {
        if (!(err instanceof ChoreographyAborted)) {
          // A script bug must not strand the screen: clean up and move on.
          console.warn("AI walkthrough step failed", err);
        }
        const stop = job.script.stop?.(job.call ?? placeholderCall(job), ctxRef.current) ?? [
          { kind: "clearGhosts" },
          { kind: "hide" },
        ];
        try {
          await runSteps(stop, ctxRef.current, { signal: new AbortController().signal, isFast: () => true });
        } catch {
          /* nothing more to do */
        }
      } finally {
        runningRef.current = null;
        abortRef.current = null;
        pump();
      }
    };
    void play();
  }, []);

  const findJob = useCallback((predicate: (job: Job) => boolean): Job | undefined => {
    const running = runningRef.current;
    if (running && predicate(running)) return running;
    return jobsRef.current.find(predicate);
  }, []);

  const enqueue = useCallback(
    (job: Job, steps: Step[]) => {
      if (steps.length > 0) job.pending.push(steps);
      if (runningRef.current === job) job.wake?.();
      else if (!jobsRef.current.includes(job)) {
        jobsRef.current.push(job);
        pump();
      }
    },
    [pump],
  );

  const onDraft = useCallback<Choreographer["onDraft"]>(
    (text) => {
      const draft = parseToolDraft(text);
      if (!draft.name) return;
      const script = getScript(draft.name);
      if (!script.draft) return;
      let job = findJob((j) => j.awaits === "call" && j.name === draft.name);
      if (!job) {
        job = {
          id: `draft:${draft.name}`,
          name: draft.name,
          script,
          call: null,
          progress: {},
          pending: [],
          awaits: "call",
        };
      }
      const steps = script.draft(draft, ctxRef.current, job.progress);
      enqueue(job, steps);
    },
    [enqueue, findJob],
  );

  const onToolCall = useCallback<Choreographer["onToolCall"]>(
    (call) => {
      if (call.read_only) return;
      const script = getScript(call.name);
      // Adopt the draft that was writing this call; drop any other draft.
      const draft = findJob((j) => j.awaits === "call");
      let job: Job;
      if (draft && draft.name === call.name) {
        job = draft;
        job.id = call.id;
        job.call = call;
        job.awaits = "result";
      } else {
        if (draft) abandonDraft(draft);
        job = { id: call.id, name: call.name, script, call, progress: {}, pending: [], awaits: "result" };
      }
      enqueue(job, script.narrate(call, ctxRef.current, job.progress));
    },
    [enqueue, findJob],
  );

  const abandonDraft = (draft: Job) => {
    if (runningRef.current === draft) {
      abortRef.current?.abort();
    } else {
      jobsRef.current = jobsRef.current.filter((j) => j !== draft);
    }
  };

  const onToolResult = useCallback<Choreographer["onToolResult"]>(
    (result) => {
      const job = findJob((j) => j.id === result.id);
      if (!job) return;
      job.result = result;
      job.wake?.();
    },
    [findJob],
  );

  const onAwaitingApproval = useCallback<Choreographer["onAwaitingApproval"]>(
    (call) => {
      const job = findJob((j) => j.id === call.id);
      if (!job) return;
      const anchor = job.script.approvalAnchor?.(call, ctxRef.current);
      if (!anchor) return;
      enqueue(job, [
        {
          kind: "spotlight",
          anchor,
          caption: ctxRef.current.t("awaitingApproval", { tool: ctxRef.current.label(call) }),
          controls: "approval",
        },
      ]);
    },
    [enqueue, findJob],
  );

  const onAbort = useCallback(() => {
    jobsRef.current = [];
    if (runningRef.current) abortRef.current?.abort();
    else ctxRef.current.spotlight.hide();
  }, []);

  const onTurnEnd = useCallback(() => {
    const draft = findJob((j) => j.awaits === "call");
    if (draft) abandonDraft(draft);
  }, [findJob]);

  return useMemo(
    () => ({ onDraft, onToolCall, onToolResult, onAwaitingApproval, onAbort, onTurnEnd, driving }),
    [onDraft, onToolCall, onToolResult, onAwaitingApproval, onAbort, onTurnEnd, driving],
  );
}

/** A stand-in for a draft that never became a call, for `stop` steps. */
function placeholderCall(job: Job): ToolCall {
  return {
    id: job.id,
    name: job.name,
    args: {},
    title: job.name,
    read_only: false,
    destructive: false,
    requires_approval: false,
    source: "mcp",
  };
}
