import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeToggle } from "@/components/theme-toggle";

const mockSetTheme = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: vi.fn(),
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("ThemeToggle", () => {
  beforeEach(async () => {
    mockSetTheme.mockClear();
    const { useTheme } = await import("next-themes");
    vi.mocked(useTheme).mockReturnValue({
      theme: "light",
      setTheme: mockSetTheme,
      resolvedTheme: "light",
    } as any);
  });

  it("calls setTheme with dark when theme is light (ternary branch)", async () => {
    const { useTheme } = await import("next-themes");
    vi.mocked(useTheme).mockReturnValue({
      theme: "light",
      setTheme: mockSetTheme,
      resolvedTheme: "light",
    } as any);

    render(<ThemeToggle />);

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /toggle theme/i }));

    expect(mockSetTheme).toHaveBeenCalledWith("dark");
  });

  it("calls setTheme with light when theme is dark (ternary branch)", async () => {
    const { useTheme } = await import("next-themes");
    vi.mocked(useTheme).mockReturnValue({
      theme: "dark",
      setTheme: mockSetTheme,
      resolvedTheme: "dark",
    } as any);

    render(<ThemeToggle />);

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /toggle theme/i }));

    expect(mockSetTheme).toHaveBeenCalledWith("light");
  });
});
