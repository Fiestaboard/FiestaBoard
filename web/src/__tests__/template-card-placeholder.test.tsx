import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TemplateCardPlaceholder } from "@/components/tiptap-template-editor/template-card-placeholder";

// FABLE-2653 §3.2: before the rich editor exists the card is already its loaded
// size: the host's title in the header row and the rows' height reserved.
describe("TemplateCardPlaceholder", () => {
  it("draws the host's title in the card header row", () => {
    render(<TemplateCardPlaceholder boardLines={6} cardTitle={<span>Template</span>} />);
    const card = document.querySelector('[data-slot="template-card-placeholder"]')!;
    expect(card).toContainElement(screen.getByText("Template"));
  });

  it("reserves the loaded rows area for the board's lines", () => {
    render(<TemplateCardPlaceholder boardLines={14} />);
    const rows = document.querySelector('[data-slot="template-card-placeholder"] > div:last-child') as HTMLElement;
    expect(rows.style.minHeight).toBe("22.25rem");
  });
});
