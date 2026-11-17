import { Dialog } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { AddDisplayDialog } from "@/components/displays/add-display-dialog";

import { server } from "./mocks/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

async function chooseArray() {
  const created = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Dialog open>
        <AddDisplayDialog onCreated={created} onCancel={vi.fn()} />
      </Dialog>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByRole("radio", { name: /Vestaboard/ }));
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await userEvent.click(await screen.findByLabelText("Board type"));
  await userEvent.click(await screen.findByRole("option", { name: "Note Array" }));
  return created;
}

describe("first-class Note Array setup", () => {
  it("tests a cloud token and creates a 2×1 array without substituting a Read/Write key", async () => {
    const tested: unknown[] = [];
    const added: unknown[] = [];
    server.use(
      http.post("/api/outputs/vestaboard/actions/test_connection", async ({ request }) => {
        tested.push(await request.json());
        return HttpResponse.json({
          status: "ok",
          message: "Array connected",
          guidance: [],
          fields: null,
          devices: null,
          geometry: {
            device_type: "note_array",
            rows: 3,
            cols: 30,
            notes_wide: 2,
            notes_tall: 1,
            matched_preset: "2 side-by-side",
          },
        });
      }),
      http.post("/api/settings/board/add", async ({ request }) => {
        const body = (await request.json()) as object;
        added.push(body);
        return HttpResponse.json({
          boards: [
            { id: "default", name: "Board", device_type: "flagship" },
            { ...body, id: "array-1" },
          ],
        });
      }),
    );
    const created = await chooseArray();
    expect(screen.getByLabelText("Cloud API Token")).toHaveAttribute("type", "password");
    expect(screen.queryByLabelText("Cloud Read/Write key")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Local API key")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add display" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Cloud API Token"), "test_array_token");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Array connected");
    await waitFor(() => expect(screen.getByRole("button", { name: "Add display" })).toBeEnabled());
    expect(added).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Add display" }));
    await waitFor(() => expect(created).toHaveBeenCalledWith("array-1"));
    expect(tested).toEqual([
      {
        output_config: {
          api_mode: "cloud",
          note_array_token: "test_array_token",
          device_type: "note_array",
          notes_wide: 2,
          notes_tall: 1,
        },
      },
    ]);
    expect(added).toEqual([
      expect.objectContaining({
        device_type: "note_array",
        notes_wide: 2,
        notes_tall: 1,
        output: "vestaboard",
        output_config: { api_mode: "cloud", note_array_token: "test_array_token" },
      }),
    ]);
  });
});
