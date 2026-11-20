/** BB-B-9: a new page's editor moves to /pages/edit/{id} after its first save. */
import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const replace = vi.fn();
let created: ((id: string) => void) | undefined;
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace, back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/hooks/use-view-transition", () => ({ useViewTransition: () => ({ push: vi.fn() }) }));
vi.mock("@/components/page-editor-shell", () => ({
  PageEditorShell: (props: { onCreated?: (id: string) => void }) => {
    created = props.onCreated;
    return null;
  },
}));

import NewPage from "../../app/routes/pages.new";

it("shows the created page's edit URL without a route change that would remount the editor", () => {
  window.history.replaceState({ idx: 3 }, "", "/pages/new");
  render(<NewPage />);
  created?.("page 42");
  expect(window.location.pathname).toBe("/pages/edit/page%2042");
  // The router's own history entry (its index) is kept.
  expect(window.history.state).toEqual({ idx: 3 });
  expect(replace).not.toHaveBeenCalled();
});
