/**
 * BB-C-18: a rejected plugin config names the field that is wrong. The hub
 * answers `{detail: {message, errors: [...]}}` with free-text messages; these
 * helpers pull them out of the ApiError and pin each one to a settings field.
 */
import { describe, expect, it } from "vitest";

import { mapConfigErrors, pluginConfigErrors } from "@/components/plugin-settings/config-errors";
import { ApiError } from "@/lib/api/core";

const properties = {
  enabled: { title: "Enable Random" },
  choices: { title: "Choices" },
  refresh_seconds: { title: "Refresh Interval (seconds)" },
  api_key: { title: "API Key" },
};

describe("pluginConfigErrors", () => {
  it("reads the per-field messages out of a validation ApiError", () => {
    const error = new ApiError("Configuration for 'random' failed validation.", 400, {
      message: "Configuration for 'random' failed validation.",
      errors: ["Refresh interval must be at least 60 seconds"],
    });
    expect(pluginConfigErrors(error)).toEqual(["Refresh interval must be at least 60 seconds"]);
  });

  it("is null for any other failure", () => {
    expect(pluginConfigErrors(new ApiError("Plugin not found", 404, "Plugin not found"))).toBeNull();
    expect(pluginConfigErrors(new Error("offline"))).toBeNull();
    expect(pluginConfigErrors(new ApiError("x", 400, { message: "x", errors: [] }))).toBeNull();
  });
});

describe("mapConfigErrors", () => {
  it("pins messages to fields by key or by title, once each", () => {
    const result = mapConfigErrors(
      [
        "Refresh interval must be at least 60 seconds",
        "Refresh interval must be at least 60 seconds",
        "choices[2] must be a non-empty string",
        "api_key is required",
      ],
      properties,
    );
    expect(result.fields).toEqual({
      refresh_seconds: ["Refresh interval must be at least 60 seconds"],
      choices: ["choices[2] must be a non-empty string"],
      api_key: ["api_key is required"],
    });
    expect(result.general).toEqual([]);
  });

  it("does not let a short title claim a message about a longer one", () => {
    const result = mapConfigErrors(["API Key must be 32 characters"], {
      api: { title: "API" },
      api_key: { title: "API Key" },
    });
    expect(result.fields).toEqual({ api_key: ["API Key must be 32 characters"] });
  });

  it("keeps a message it cannot place as a general error", () => {
    const result = mapConfigErrors(["Could not reach the service"], properties);
    expect(result.fields).toEqual({});
    expect(result.general).toEqual(["Could not reach the service"]);
  });
});
