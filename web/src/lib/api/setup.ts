// Setup wizard domain: board connection testing, Local API
// enablement, network discovery, and the welcome message.

import type { ConfigValidationResponse } from "./boards";
import { fetchApi } from "./core";

// Setup wizard types
export interface BoardTestRequest {
  api_mode: "local" | "cloud";
  local_api_key?: string;
  cloud_key?: string;
  host?: string;
  /** Local API port (default 7000). Local-array tiles can sit on other ports. */
  port?: number;
}

export interface BoardTestResponse {
  success: boolean;
  message: string;
  error?: string;
  api_mode?: string;
  troubleshooting?: string[];
}

/**
 * `POST /send-welcome-message` (Phase 2 Task 8 conventions pass).
 *
 * The `status: "blocked" | "success"` envelope is gone. A silence window or a
 * paused board is now a 409 that `fetchApi` throws as an `ApiError`, and
 * `sent: false` means only "the board already showed this" — see
 * `src/board_api/routes.py`.
 */
export interface WelcomeMessageResponse {
  message: string;
  sent: boolean;
}

export interface EnableLocalApiRequest {
  host: string;
  enablement_token: string;
}

export interface EnableLocalApiResponse {
  success: boolean;
  api_key?: string;
  message: string;
  error?: string;
}

export interface DiscoveredBoard {
  ip: string;
  port: number;
  hostname: string;
  source: "mdns" | "port_scan";
}

export interface BoardScanResponse {
  boards: DiscoveredBoard[];
}

export const setupApi = {
  // Setup wizard endpoints
  validateSetup: () => fetchApi<ConfigValidationResponse>("/config/validate"),

  testBoardConnection: (request: BoardTestRequest) =>
    fetchApi<BoardTestResponse>("/config/board/test", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  sendWelcomeMessage: () =>
    fetchApi<WelcomeMessageResponse>("/send-welcome-message", {
      method: "POST",
    }),

  enableLocalApi: (request: EnableLocalApiRequest) =>
    fetchApi<EnableLocalApiResponse>("/config/board/enable-local-api", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  scanForBoards: (timeout?: number) =>
    fetchApi<BoardScanResponse>("/config/board/scan", {
      method: "POST",
      body: JSON.stringify({ timeout: timeout ?? 4.0 }),
    }),
};
