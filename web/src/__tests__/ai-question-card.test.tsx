import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AiQuestionCard } from "@/components/ai-question-card";
import type { Elicitation } from "@/lib/ai-chat-types";

const QUESTION: Elicitation = {
  id: "q1",
  name: "ask_user",
  message: "Which board?",
  requested_schema: {
    type: "object",
    properties: { answer: { type: "string", title: "Answer", enum: ["Kitchen", "Hall"] } },
    required: ["answer"],
  },
  allow_free_text: true,
};

describe("AiQuestionCard", () => {
  it("renders the options as one-click chips that answer with the choice", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<AiQuestionCard elicitation={QUESTION} onAnswer={onAnswer} />);

    expect(screen.getByRole("group", { name: "Which board?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kitchen" }));

    expect(onAnswer).toHaveBeenCalledWith({ action: "accept", content: { answer: "Kitchen" } });
  });

  it("Skip declines", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<AiQuestionCard elicitation={QUESTION} onAnswer={onAnswer} />);
    await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(onAnswer).toHaveBeenCalledWith({ action: "decline" });
  });

  it("collapses to what was answered", () => {
    render(
      <AiQuestionCard
        elicitation={{ ...QUESTION, answer: { action: "accept", content: { answer: "Hall" } } }}
        onAnswer={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Kitchen" })).not.toBeInTheDocument();
    expect(screen.getByText(/You answered: Hall/)).toBeInTheDocument();
  });

  it("offers no chips for a free-text question", () => {
    render(
      <AiQuestionCard
        elicitation={{ ...QUESTION, requested_schema: { type: "object", properties: { answer: { type: "string" } } } }}
        onAnswer={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Kitchen" })).not.toBeInTheDocument();
    expect(screen.getByText(/type an answer below/i)).toBeInTheDocument();
  });
});
