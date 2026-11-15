import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));

import ProfilePage from "../../app/routes/profile";

describe("/profile", () => {
  it("opens Settings › Account (WEB-01: Profile retired into Settings)", () => {
    render(<ProfilePage />);
    expect(replace).toHaveBeenCalledWith("/settings/account");
  });
});
