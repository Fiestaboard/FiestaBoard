import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import routes from "../../app/routes";
import NotFound from "../../app/routes/not-found";

// BB-A-9: an unknown URL renders inside the app shell (header, nav) with a
// way back Home, instead of React Router's bare "404 Not Found".
describe("an unknown URL", () => {
  it("is caught by a route inside the shell", () => {
    const paths = (routes as Array<{ path?: string; file: string }>).map((r) => r.path);
    expect(paths).toContain("*");
  });

  it("says the page was not found, in a main landmark, with a link Home", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Home" })).toHaveAttribute("href", "/");
  });
});
