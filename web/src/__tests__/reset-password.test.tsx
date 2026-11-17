import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import ResetPassword from "../../app/routes/reset-password";
import { server } from "./mocks/server";

it("redeems an owner-minted code without signing in and clears the secrets on success", async () => {
  let payload: unknown;
  server.use(
    http.post("/api/auth/password-reset", async ({ request }) => {
      payload = await request.json();
      return HttpResponse.json({ status: "ok" });
    }),
  );
  const user = userEvent.setup();
  render(<ResetPassword />);
  await user.type(screen.getByLabelText("Reset code"), "fb_reset_one-time");
  await user.type(screen.getByLabelText("New password"), "new secret password");
  await user.type(screen.getByLabelText("Confirm new password"), "new secret password");
  await user.click(screen.getByRole("button", { name: "Reset password" }));
  expect(await screen.findByRole("heading", { name: "Password reset" })).toHaveFocus();
  expect(payload).toEqual({ code: "fb_reset_one-time", new_password: "new secret password" });
  expect(screen.queryByLabelText("Reset code")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.getByText(/Every browser, TV and phone has been signed out/)).toBeInTheDocument();
});

it("blocks mismatched passwords without consuming the code", async () => {
  let requests = 0;
  server.use(
    http.post("/api/auth/password-reset", () => {
      requests++;
      return HttpResponse.json({ status: "ok" });
    }),
  );
  const user = userEvent.setup();
  render(<ResetPassword />);
  await user.type(screen.getByLabelText("Reset code"), "fb_reset_one-time");
  await user.type(screen.getByLabelText("New password"), "new secret password");
  await user.type(screen.getByLabelText("Confirm new password"), "different password");
  await user.click(screen.getByRole("button", { name: "Reset password" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match");
  expect(requests).toBe(0);
});

it.each([400, 429, 500])("keeps recovery actionable after HTTP %s", async (status) => {
  server.use(http.post("/api/auth/password-reset", () => HttpResponse.json({ error: "invalid_grant" }, { status })));
  const user = userEvent.setup();
  render(<ResetPassword />);
  await user.type(screen.getByLabelText("Reset code"), "fb_reset_one-time");
  await user.type(screen.getByLabelText("New password"), "new secret password");
  await user.type(screen.getByLabelText("Confirm new password"), "new secret password");
  await user.click(screen.getByRole("button", { name: "Reset password" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      status === 400 ? /invalid or has expired/ : status === 429 ? /Too many attempts/ : /Unable to reset/,
    ),
  );
  expect(screen.getByLabelText("Reset code")).toHaveFocus();
  expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();
});
