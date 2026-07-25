import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import { BoardDisplay } from "@/components/board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("BoardDisplay tile coordinates", () => {
  it("exposes data-row/data-col on static tiles with cell values", () => {
    const { container } = render(<BoardDisplay message={"A{red}"} isStatic />, { wrapper: TestWrapper });
    const a = container.querySelector('[data-row="0"][data-col="0"]');
    const red = container.querySelector('[data-row="0"][data-col="1"]');
    expect(a).not.toBeNull();
    expect(a!.getAttribute("data-cell-value")).toBe("A");
    expect(red!.getAttribute("data-cell-value")).toBe("red");
    // full flagship grid present
    expect(container.querySelector('[data-row="5"][data-col="21"]')).not.toBeNull();
  });

  it("exposes data-row/data-col on animated tiles", () => {
    const { container } = render(<BoardDisplay message={"HI"} />, { wrapper: TestWrapper });
    expect(container.querySelector('[data-row="0"][data-col="1"]')).not.toBeNull();
  });
});
