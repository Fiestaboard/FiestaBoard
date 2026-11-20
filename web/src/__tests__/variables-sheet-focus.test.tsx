/**
 * BB-B-21 (Figma 57:66161): on a touch screen the Variables picker opens
 * showing its groups; the keyboard comes up only when the search is tapped.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

const picked = vi.fn();
vi.mock("@/components/tiptap-template-editor/components/VariablePickerContent", () => ({
  VariablePickerContent: (props: { autoFocusSearch?: boolean }) => {
    picked(props.autoFocusSearch);
    return <span>picker</span>;
  },
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getTemplateVariables: vi.fn().mockResolvedValue({ variables: { weather: ["temperature"] }, colors: {} }),
    },
  };
});

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";

function media(phone: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (q) =>
      ({
        matches: phone ? q.includes("max-width") : false,
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  picked.mockClear();
});

async function openVariables() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TemplateEditorToolbar editor={null} />
    </QueryClientProvider>,
  );
  const button = await screen.findByRole("button", { name: "Variables" });
  await vi.waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  await screen.findByText("picker");
}

it("does not focus the search on a phone", async () => {
  media(true);
  await openVariables();
  expect(picked).toHaveBeenLastCalledWith(false);
});

it("still focuses the search with a mouse and keyboard", async () => {
  media(false);
  await openVariables();
  expect(picked).toHaveBeenLastCalledWith(true);
});
