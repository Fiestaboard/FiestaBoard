import { describe, expect, it } from "vitest";

import { deriveChatActivity } from "@/lib/ai-chat-activity";
import type { ChatMessage, ToolCallDisplay, ToolPhase } from "@/lib/ai-chat-types";

function call(phase: ToolPhase): ToolCallDisplay {
  return {
    id: "call-1",
    name: "get_display_info",
    title: "Inspect display",
    args: {},
    read_only: true,
    destructive: false,
    requires_approval: false,
    source: "mcp",
    phase,
  };
}
const turn = (message: Partial<ChatMessage>): ChatMessage[] => [
  { role: "user", content: "Make art" },
  { role: "assistant", content: "", ...message },
];

describe("FiestaBot activity", () => {
  it("is ready for an empty conversation", () => {
    expect(deriveChatActivity([], "idle").state).toBe("idle");
  });
  it("distinguishes thinking from a streamed reply", () => {
    expect(deriveChatActivity(turn({ pending: true }), "streaming").state).toBe("thinking");
    expect(deriveChatActivity(turn({ pending: true, content: "Here is your scene" }), "streaming").state).toBe(
      "writing",
    );
  });
  it("honors a new thinking event after earlier commentary", () => {
    expect(
      deriveChatActivity(
        turn({ pending: true, content: "I will check the display.", status: { phase: "thinking", toolCallId: null } }),
        "streaming",
      ).state,
    ).toBe("thinking");
  });
  it("names the real running call instead of claiming it is still thinking", () => {
    const tool = call("running");
    expect(
      deriveChatActivity(turn({ pending: true, content: "I will inspect it", toolCalls: [tool] }), "streaming"),
    ).toMatchObject({ state: "running", tool });
  });
  it("shows preparation before a tool actually runs", () => {
    expect(
      deriveChatActivity(turn({ pending: true, draft: { op: "create_page", text: '{"name":"Sunset"' } }), "streaming")
        .state,
    ).toBe("preparing");
  });
  it.each(["awaiting_approval", "awaiting_input"] as const)("keeps %s visible when streaming has paused", (status) => {
    expect(deriveChatActivity(turn({}), status).state).toBe(status === "awaiting_approval" ? "approval" : "input");
  });
  it("does not claim a failed tool completed successfully", () => {
    expect(deriveChatActivity(turn({ toolCalls: [call("error")] }), "idle").state).toBe("error");
  });
  it.each(["stopped", "denied"] as const)("keeps %s distinct from failure and completion", (phase) => {
    expect(deriveChatActivity(turn({ toolCalls: [call(phase)] }), "idle").state).toBe(phase);
  });
  it("does not carry an old error into a later successful turn", () => {
    const messages = [...turn({ toolCalls: [call("error")] }), ...turn({ content: "Done" })];
    expect(deriveChatActivity(messages, "idle").state).toBe("complete");
  });
  it("shows a turn limit as a pause, not completion", () => {
    expect(deriveChatActivity(turn({ content: "More to do" }), "idle", null, true).state).toBe("paused");
  });
  it("keeps a connection failure visible even without a tool error", () => {
    expect(deriveChatActivity(turn({}), "error", "Connection lost").state).toBe("error");
  });
});
