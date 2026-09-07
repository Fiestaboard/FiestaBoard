import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useRouter } from "@/hooks/use-router";

const navigate = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigate,
  useLocation: () => ({ pathname: "/" }),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

describe("useRouter", () => {
  it("forwards { scroll: false } to react-router as preventScrollReset", () => {
    navigate.mockClear();
    const { result } = renderHook(() => useRouter());

    result.current.replace("/settings?section=general", { scroll: false });

    expect(navigate).toHaveBeenCalledWith("/settings?section=general", {
      replace: true,
      preventScrollReset: true,
    });
  });

  it("does not prevent scroll reset by default", () => {
    navigate.mockClear();
    const { result } = renderHook(() => useRouter());

    result.current.push("/pages");

    expect(navigate).toHaveBeenCalledWith("/pages", { preventScrollReset: false });
  });
});
