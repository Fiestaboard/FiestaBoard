import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HELP_DOCS_URL } from "@/lib/nav-items";

import routes from "../../app/routes";
import NotFound from "../../app/routes/not-found";

// BB-A-9 (07e `329:50241`): an unknown URL renders inside the app shell (header,
// nav) as a centred "Page not found" naming the address, with Go to Home and
// Help & Docs, instead of React Router's bare "404 Not Found".
describe("an unknown URL", () => {
  it("is caught by a route inside the shell", () => {
    const paths = (routes as Array<{ path?: string; file: string }>).map((r) => r.path);
    expect(paths).toContain("*");
  });

  it("says nothing is at that address, with the ways forward", () => {
    window.history.replaceState(null, "", "/pagez");
    render(<NotFound />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(
      screen.getByText(
        `There’s nothing at ${window.location.host}/pagez. The link may have a typo, or the page moved.`,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Help & Docs" })).toHaveAttribute("href", HELP_DOCS_URL);
    window.history.replaceState(null, "", "/");
  });
});
