// Outputs domain: the installed outputs, board-settings actions (plan D13),
// boards for output plugins, and the setup wizard's stored outcome.
// Mirrors src/outputs/models.py and src/settings/models.py (WizardStateBody).

import { fetchApi } from "./core";

/** One button of an output's board settings screen. */
export interface OutputActionDescriptor {
  id: string;
  label: string;
  description: string;
  /** test_connection, discover, identify or detect_geometry: a core hook. */
  builtin: boolean;
  /** JSON Schema of the action's input (the settings vocabulary), if any. */
  input_schema: Record<string, unknown> | null;
  /** Declared result fields: whether each is secret and which setting it fills. */
  result_fields: Record<string, { secret: boolean; fills: string | null }>;
  /** `ui:visible_when` over the settings and the board's `@` facts: shown only while it holds. */
  visible_when?: Record<string, unknown> | null;
  /** Apply the result's geometry without asking. */
  auto_apply?: boolean;
}

export interface OutputDeviceModel {
  id: string;
  label: string;
}

/** `GET /outputs` — an installed output. */
export interface OutputSummary {
  id: string;
  name: string;
  description: string;
  /** A Lucide icon name. */
  icon: string | null;
  /** Vestaboard and FiestaPanel: created through their own flows. */
  builtin: boolean;
  /** A third-party output plugin, usable only with the output plugins beta. */
  beta_gated: boolean;
  /** Whether a board can use it now (false: the beta is off). */
  available: boolean;
  output_api: number | null;
  capabilities: {
    technology: string;
    delivery: string;
    animation: string;
    native_transitions: string[];
    charset: string | null;
  };
  device_models: OutputDeviceModel[];
  /** JSON Schema of `output_config`, with ui:sections / ui:visible_when / ui:widget. */
  settings_schema: Record<string, unknown>;
  actions: OutputActionDescriptor[];
}

/**
 * `GET /outputs/available` — an output the user can pick, installed or not
 * (plan D18). Mirrors `AvailableOutput` in src/outputs/models.py.
 */
export interface AvailableOutput {
  id: string;
  name: string;
  description: string;
  /** A Lucide icon name. */
  icon: string | null;
  /** installed: usable now; seed: bundled with this image (installs offline); registry: installs from its repository. */
  source: "installed" | "seed" | "registry";
  installed: boolean;
  /** Vestaboard and FiestaPanel: created through their own flows. */
  builtin: boolean;
  /** Usable only with the output plugins beta. */
  beta_gated: boolean;
  /** Whether it can be installed and used now (false: the beta is off). */
  available: boolean;
  /** Installing it fetches its repository. */
  needs_network: boolean;
  output_api: number | null;
}

export interface ActionResultField {
  value: unknown;
  /** A credential: never logged, stored through the secret path. */
  secret: boolean;
  /** The settings field to fill; `null` = the result field's own name. */
  fills: string | null;
}

/** A detected board size: the `detect-size` shape (`DetectBoardSizeResponse`). */
export interface ActionGeometry {
  device_type: "flagship" | "note" | "note_array" | "panel";
  rows: number;
  cols: number;
  notes_wide: number | null;
  notes_tall: number | null;
  matched_preset: string | null;
}

export interface DiscoveredDevice {
  ip: string;
  port: number;
  hostname: string | null;
  source: string | null;
  label: string | null;
}

/**
 * Every action's answer. `status: "error"` is the device's verdict at 200; a
 * refusal before the device was contacted is a 4xx (thrown as `ApiError`).
 */
export interface ActionResult {
  status: "ok" | "error" | "warning";
  message: string;
  guidance: string[];
  fields: Record<string, ActionResultField> | null;
  geometry: ActionGeometry | null;
  devices: DiscoveredDevice[] | null;
}

/** `POST /outputs/{output_id}/boards` body. */
export interface OutputBoardCreate {
  name?: string;
  device_model: string;
  output_config: Record<string, unknown>;
  geometry?: { rows?: number; cols?: number; notes_wide?: number; notes_tall?: number };
}

export interface OutputBoardResponse {
  id: string;
  name: string;
  output: string;
  device_model: string;
  charset: string | null;
  device_type: string;
  rows: number;
  cols: number;
  output_config: Record<string, unknown>;
}

export type WizardState = "completed" | "skipped" | null;

export const outputsApi = {
  listOutputs: () => fetchApi<OutputSummary[]>("/outputs"),

  /** Every output that can be picked, installed or not (the setup wizard's first step). */
  listAvailableOutputs: () => fetchApi<AvailableOutput[]>("/outputs/available"),

  /** Install an output (the seed offline, else the registry); answers it as `GET /outputs` lists it. Idempotent. */
  installOutput: (outputId: string) =>
    fetchApi<OutputSummary>(`/outputs/${encodeURIComponent(outputId)}/install`, {
      method: "POST",
      // A registry install clones a repository (up to two minutes on a slow link).
      timeoutMs: 180_000,
    }),

  /** Run an action on settings typed before a board exists. */
  runDraftOutputAction: (
    outputId: string,
    action: string,
    body: { output_config: Record<string, unknown>; input?: Record<string, unknown>; device_model?: string },
  ) =>
    fetchApi<ActionResult>(`/outputs/${encodeURIComponent(outputId)}/actions/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 30_000,
    }),

  /** Run an action on a saved board; `"***"` in `output_config` is restored server-side. */
  runBoardAction: (
    boardId: string,
    action: string,
    body: { input?: Record<string, unknown>; output_config?: Record<string, unknown> },
  ) =>
    fetchApi<ActionResult>(`/boards/${encodeURIComponent(boardId)}/actions/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 30_000,
    }),

  createOutputBoard: (outputId: string, body: OutputBoardCreate) =>
    fetchApi<OutputBoardResponse>(`/outputs/${encodeURIComponent(outputId)}/boards`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getWizardState: () => fetchApi<{ state: WizardState }>("/settings/wizard"),

  setWizardState: (state: WizardState) =>
    fetchApi<{ state: WizardState }>("/settings/wizard", {
      method: "PUT",
      body: JSON.stringify({ state }),
    }),
};
