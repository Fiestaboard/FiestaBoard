import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ModelCombobox } from "@/components/model-combobox";
import type { AIModel } from "@/lib/api";

const MODELS: AIModel[] = [
  { id: "openai/gpt-test", name: "GPT Test" },
  { id: "anthropic/claude-test", name: "Claude Test" },
  { id: "plain-id", name: "plain-id" },
];

function Harness({ models = MODELS, onPick }: { models?: AIModel[]; onPick: (id: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <ModelCombobox
      aria-label="Model"
      models={models}
      value={value}
      onValueChange={(id) => {
        setValue(id);
        onPick(id);
      }}
    />
  );
}

describe("ModelCombobox", () => {
  it("shows each model's name with its id", async () => {
    const user = userEvent.setup();
    render(<Harness onPick={vi.fn()} />);
    await user.click(screen.getByRole("combobox", { name: "Model" }));
    const option = await screen.findByRole("option", { name: /GPT Test/ });
    expect(option).toHaveTextContent("openai/gpt-test");
  });

  it("narrows the list as you type, by name or by id", async () => {
    const user = userEvent.setup();
    render(<Harness onPick={vi.fn()} />);
    await user.type(screen.getByRole("combobox", { name: "Model" }), "claude");
    expect(await screen.findByRole("option", { name: /Claude Test/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /GPT Test/ })).not.toBeInTheDocument();
  });

  it("renders only the first matches of a long list and says so", async () => {
    const many = Array.from({ length: 400 }, (_, i) => ({ id: `vendor/model-${i}`, name: `Model ${i}` }));
    const user = userEvent.setup();
    render(<Harness models={many} onPick={vi.fn()} />);
    await user.type(screen.getByRole("combobox", { name: "Model" }), "model");
    const list = await screen.findByRole("listbox");
    expect(within(list).getAllByRole("option").length).toBeLessThanOrEqual(101);
    expect(screen.getByText(/Showing first/)).toBeInTheDocument();
  });

  it("accepts a model id typed by hand that the provider did not list", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<Harness onPick={onPick} />);
    await user.type(screen.getByRole("combobox", { name: "Model" }), "my-org/custom-1");
    await user.click(await screen.findByRole("option", { name: /my-org\/custom-1/ }));
    expect(onPick).toHaveBeenCalledWith("my-org/custom-1");
  });

  it("works with no list at all, by typing", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<Harness models={[]} onPick={onPick} />);
    await user.type(screen.getByRole("combobox", { name: "Model" }), "typed-model");
    await user.click(await screen.findByRole("option", { name: /typed-model/ }));
    expect(onPick).toHaveBeenCalledWith("typed-model");
  });
});
