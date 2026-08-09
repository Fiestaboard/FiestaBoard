import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";
import { insertTemplateContent } from "@/components/tiptap-template-editor/utils/insertion";
import { parseLineContent } from "@/components/tiptap-template-editor/utils/serialization";
import type { HomeAssistantEntity } from "@/lib/api";

import { mockTemplateVariables } from "./mocks/handlers";
import { server } from "./mocks/server";

// The insertion helper is the seam between the toolbar and TipTap: spying on it
// lets us assert the exact template string without standing up a real editor.
vi.mock("@/components/tiptap-template-editor/utils/insertion", () => ({
  insertTemplateContent: vi.fn(),
}));

const insertSpy = vi.mocked(insertTemplateContent);

const API_BASE = "/api";

const HA_BUTTON_LABEL = "Home Assistant entities";

const sensorTemperature: HomeAssistantEntity = {
  entity_id: "sensor.temperature",
  state: "72",
  attributes: { unit_of_measurement: "°F" },
  friendly_name: "Living Room Temperature",
};

/** `/templates/variables` including a `home_assistant` namespace. */
function useHomeAssistantVariables() {
  server.use(
    http.get(`${API_BASE}/templates/variables`, () =>
      HttpResponse.json({
        ...mockTemplateVariables,
        variables: { ...mockTemplateVariables.variables, home_assistant: ["sensor_temperature.state"] },
      }),
    ),
  );
}

/**
 * `/home-assistant/entities` returning `entities`, plus a counter so tests can
 * assert the request is only made once the dialog is actually opened.
 */
function useEntities(entities: HomeAssistantEntity[]) {
  const calls = { count: 0 };
  server.use(
    http.get(`${API_BASE}/home-assistant/entities`, () => {
      calls.count += 1;
      return HttpResponse.json({ entities });
    }),
  );
  return calls;
}

function renderToolbar(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (extra: Record<string, unknown>) => (
    <QueryClientProvider client={queryClient}>
      <TemplateEditorToolbar editor={null} {...props} {...extra} />
    </QueryClientProvider>
  );
  const result = render(ui({}));
  return { ...result, rerenderWith: (extra: Record<string, unknown>) => result.rerender(ui(extra)) };
}

/** Minimal editor stand-in: enough surface for the toolbar's effects. */
function makeFakeEditor() {
  return {
    can: () => ({ undo: () => false, redo: () => false }),
    state: { selection: { from: 0, to: 0 }, doc: { textBetween: () => "" } },
    on: vi.fn(),
    off: vi.fn(),
  };
}

/** Open the picker and drive it to "sensor.temperature" → "state". */
async function chooseTemperatureState(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByLabelText(HA_BUTTON_LABEL));
  await user.click(await screen.findByText("sensor.temperature"));
  await user.click(await screen.findByText("state"));
}

describe("TemplateEditorToolbar Home Assistant entity picker", () => {
  beforeEach(() => {
    insertSpy.mockReset();
  });

  it("renders the Home Assistant entity button when template variables include home_assistant", async () => {
    useHomeAssistantVariables();
    renderToolbar();

    expect(await screen.findByLabelText(HA_BUTTON_LABEL)).toBeInTheDocument();
  });

  it("does not render the Home Assistant entity button when home_assistant is absent", async () => {
    // The default `/templates/variables` mock only exposes weather + datetime.
    renderToolbar();

    // Wait for the toolbar to have consumed the variables response.
    expect(await screen.findByLabelText("Variables")).toBeInTheDocument();
    expect(screen.queryByLabelText(HA_BUTTON_LABEL)).toBeNull();
  });

  it("does not render the Home Assistant entity button in draw mode", async () => {
    useHomeAssistantVariables();
    const { rerenderWith } = renderToolbar({ onDrawModeToggle: () => {}, onDrawBrushChange: () => {} });

    // Present first, so we know the variables query resolved with home_assistant.
    expect(await screen.findByLabelText(HA_BUTTON_LABEL)).toBeInTheDocument();

    rerenderWith({ drawMode: true });

    expect(screen.getByTestId("draw-color-eraser")).toBeInTheDocument();
    expect(screen.queryByLabelText(HA_BUTTON_LABEL)).toBeNull();
  });

  it("opens the entity picker dialog when the button is clicked", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar();

    await user.click(await screen.findByLabelText(HA_BUTTON_LABEL));

    expect(await screen.findByText("Select Home Assistant Entity")).toBeInTheDocument();
    expect(await screen.findByText("sensor.temperature")).toBeInTheDocument();
  });

  it("inserts exactly {{home_assistant.sensor_temperature.state}} when an entity and attribute are confirmed", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);
    await user.click(screen.getByRole("button", { name: "Insert" }));

    await waitFor(() => expect(insertSpy).toHaveBeenCalledTimes(1));
    expect(insertSpy.mock.calls[0][1]).toBe("{{home_assistant.sensor_temperature.state}}");
  });

  it("closes the dialog after inserting, and stays closed when onClose fires twice", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);
    await user.click(screen.getByRole("button", { name: "Insert" }));

    // The picker calls onSelect -> onClose, and the dialog's own
    // onOpenChange(false) calls onClose again: both must be harmless.
    await waitFor(() => expect(screen.queryByText("Select Home Assistant Entity")).toBeNull());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText("Select Home Assistant Entity")).toBeNull();
    expect(insertSpy).toHaveBeenCalledTimes(1);
  });

  it("does not request entities until the dialog is opened", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    const entityCalls = useEntities([sensorTemperature]);
    renderToolbar();

    const button = await screen.findByLabelText(HA_BUTTON_LABEL);
    // Toolbar rendered (and the variables query settled) with the picker mounted
    // but closed — the entities endpoint must still be untouched.
    expect(entityCalls.count).toBe(0);

    await user.click(button);

    await waitFor(() => expect(entityCalls.count).toBe(1));
  });

  it("leaves focus in the editor after inserting instead of on the toolbar button", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);

    // Stand-in for the ProseMirror surface: the real `insertTemplateContent`
    // runs `editor.chain().focus()`, so focusing here mirrors production.
    const editorSurface = document.createElement("div");
    editorSurface.tabIndex = -1;
    document.body.appendChild(editorSurface);
    insertSpy.mockImplementation(() => editorSurface.focus());

    try {
      renderToolbar({ editor: makeFakeEditor() });

      await chooseTemperatureState(user);
      await user.click(screen.getByRole("button", { name: "Insert" }));

      await waitFor(() => expect(insertSpy).toHaveBeenCalledTimes(1));
      // The dialog restores focus to whatever was focused before it opened
      // (the toolbar button). Inserting before that happens loses the caret.
      await waitFor(() => expect(document.activeElement).toBe(editorSurface));
      expect(document.activeElement?.isConnected).toBe(true);
    } finally {
      editorSurface.remove();
    }
  });

  it("emits a string the editor's parser turns into a single home_assistant variable node", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);
    await user.click(screen.getByRole("button", { name: "Insert" }));
    await waitFor(() => expect(insertSpy).toHaveBeenCalledTimes(1));

    // No bespoke TipTap node is needed: the existing parser splits on the first
    // dot, so the emitted string must round-trip as a plain variable pill.
    const variableNodes = parseLineContent(insertSpy.mock.calls[0][1]).filter((node) => node.type === "variable");
    expect(variableNodes).toHaveLength(1);
    expect(variableNodes[0].attrs).toMatchObject({ pluginId: "home_assistant", field: "sensor_temperature.state" });
  });

  it("starts from the entity list again when the picker is reopened after an insert", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);
    await user.click(screen.getByRole("button", { name: "Insert" }));
    await waitFor(() => expect(screen.queryByText("Select Home Assistant Entity")).toBeNull());

    await user.click(screen.getByLabelText(HA_BUTTON_LABEL));

    // Back on the entity list (search box present), not the attribute step.
    expect(await screen.findByLabelText("Search entities")).toBeInTheDocument();
    expect(screen.queryByText("Select Attribute")).toBeNull();
  });

  it("cancels the deferred insertion if the toolbar unmounts before the frame runs", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    const { unmount } = renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);

    // Confirm and unmount in one synchronous block: no `await` in between, so
    // the scheduled frame provably cannot have run yet on any machine.
    fireEvent.click(screen.getByRole("button", { name: "Insert" }));
    expect(insertSpy).not.toHaveBeenCalled();
    unmount();

    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(insertSpy).not.toHaveBeenCalled();
  });

  it("renders the empty state when Home Assistant returns no entities", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([]);
    renderToolbar({ editor: makeFakeEditor() });

    await user.click(await screen.findByLabelText(HA_BUTTON_LABEL));

    expect(await screen.findByText("No entities found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Insert" })).toBeDisabled();
  });

  it("closes without inserting when Cancel is clicked", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByText("Select Home Assistant Entity")).toBeNull());
    expect(insertSpy).not.toHaveBeenCalled();
  });

  it("closes without inserting when Escape is pressed", async () => {
    const user = userEvent.setup();
    useHomeAssistantVariables();
    useEntities([sensorTemperature]);
    renderToolbar({ editor: makeFakeEditor() });

    await chooseTemperatureState(user);
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByText("Select Home Assistant Entity")).toBeNull());
    expect(insertSpy).not.toHaveBeenCalled();
  });
});
