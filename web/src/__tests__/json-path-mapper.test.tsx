import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type JSONSchema, SchemaForm } from "@/components/plugin-settings";
import type * as apiModule from "@/lib/api";

const testFetch = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof apiModule>("@/lib/api");
  return {
    ...actual,
    api: { ...actual.api, genericDataTestFetch: (...args: unknown[]) => testFetch(...args) },
  };
});

/**
 * `json-path-mapper` is the capability-named successor to
 * `generic-data-mapping-helper`: probe an endpoint, browse the JSON, map paths
 * in it onto template variables. The widget used to know one plugin's field
 * names and one plugin's variable prefix; both now come from the manifest and
 * from the surrounding plugin context.
 */

function mapperSchema(widget: string, uiOptions?: Record<string, unknown>): JSONSchema {
  return {
    type: "object",
    properties: {
      mappings: {
        type: "array",
        title: "Variable Mappings",
        "ui:widget": widget,
        ...(uiOptions ? { "ui:options": uiOptions } : {}),
        items: {
          type: "object",
          properties: {
            variable: { type: "string" },
            path: { type: "string" },
            default: { type: "string" },
          },
        },
      },
    },
  };
}

function Harness({
  schema,
  initial,
  pluginId,
  onChange,
}: {
  schema: JSONSchema;
  initial: Record<string, unknown>;
  pluginId?: string;
  onChange?: (values: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(initial);
  return (
    <SchemaForm
      schema={schema}
      values={values}
      onChange={(next) => {
        setValues(next);
        onChange?.(next);
      }}
      pluginId={pluginId}
    />
  );
}

describe("json-path-mapper widget", () => {
  beforeEach(() => {
    testFetch.mockReset();
    testFetch.mockResolvedValue({ data: {} });
  });

  it("renders the mapping helper, not a plain array field", () => {
    render(<Harness schema={mapperSchema("json-path-mapper")} initial={{ mappings: [] }} />);

    expect(screen.getByRole("button", { name: "Test & Preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add mapping/i })).toBeInTheDocument();
  });

  it("still renders the mapping helper under its deprecated widget name", () => {
    render(<Harness schema={mapperSchema("generic-data-mapping-helper")} initial={{ mappings: [] }} />);

    expect(screen.getByRole("button", { name: "Test & Preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add mapping/i })).toBeInTheDocument();
  });

  it("probes using the sibling properties named in ui:options.probe", async () => {
    const user = userEvent.setup();
    // Deliberately none of generic-data's field names: if any part of the
    // request still arrives, the widget read it from the manifest.
    const schema = mapperSchema("json-path-mapper", {
      probe: {
        url: "endpoint",
        format: "response_type",
        method: "verb",
        headers: "extra_headers",
        body: "payload",
      },
    });
    schema.properties.endpoint = { type: "string", title: "Endpoint" };
    schema.properties.response_type = { type: "string", title: "Response Type" };
    schema.properties.verb = { type: "string", title: "Verb" };
    schema.properties.payload = { type: "string", title: "Payload" };

    render(
      <Harness
        schema={schema}
        initial={{
          endpoint: "https://example.com/feed",
          response_type: "xml",
          verb: "POST",
          extra_headers: [{ name: "X-Token", value: "example_token" }],
          payload: '{"q":1}',
          mappings: [],
        }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Test & Preview" }));

    await waitFor(() => expect(testFetch).toHaveBeenCalledTimes(1));
    expect(testFetch).toHaveBeenCalledWith({
      url: "https://example.com/feed",
      format: "xml",
      method: "POST",
      headers: [{ name: "X-Token", value: "example_token" }],
      body: '{"q":1}',
    });
  });

  it("names the surrounding plugin in the template hint", () => {
    render(
      <Harness
        schema={mapperSchema("json-path-mapper")}
        initial={{ mappings: [{ variable: "temp", path: "current.temp_f", default: "" }] }}
        pluginId="tide_clock"
      />,
    );

    expect(screen.getByText("{{tide_clock.temp}}")).toBeInTheDocument();
    expect(screen.queryByText("{{generic_data.temp}}")).not.toBeInTheDocument();
  });

  const remappedKeys = { keys: { variable: "name", path: "json_path", default: "fallback" } };

  it("reads existing rows through the keys named in ui:options.keys", () => {
    render(
      <Harness
        schema={mapperSchema("json-path-mapper", remappedKeys)}
        initial={{ mappings: [{ name: "temp", json_path: "current.temp_f", fallback: "n/a" }] }}
      />,
    );

    expect(screen.getByLabelText("Variable Name")).toHaveValue("temp");
    expect(screen.getByLabelText("Data Path")).toHaveValue("current.temp_f");
    expect(screen.getByLabelText("Default Value")).toHaveValue("n/a");
  });

  it("writes edits back through the keys named in ui:options.keys", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Harness
        schema={mapperSchema("json-path-mapper", remappedKeys)}
        initial={{ mappings: [{ name: "temp", json_path: "current.temp_f", fallback: "" }] }}
        onChange={onChange}
      />,
    );

    await user.type(screen.getByLabelText("Data Path"), "x");

    const last = onChange.mock.calls.at(-1)?.[0] as { mappings: Record<string, unknown>[] };
    expect(last.mappings).toEqual([{ name: "temp", json_path: "current.temp_fx", fallback: "" }]);
  });

  /**
   * generic-data's manifest declares neither block today. Its field names are
   * the defaults, so it has to keep working before its own migration lands.
   */
  it("falls back to the original field names when ui:options declares neither block", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const schema = mapperSchema("generic-data-mapping-helper");
    schema.properties.url = { type: "string", title: "Data URL" };
    schema.properties.format = { type: "string", title: "Response Format" };
    schema.properties.method = { type: "string", title: "HTTP Method" };

    render(
      <Harness
        schema={schema}
        initial={{
          url: "https://example.com/data.json",
          format: "json",
          method: "GET",
          headers: [],
          mappings: [{ variable: "temp", path: "current.temp_f", default: "" }],
        }}
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText("Variable Name")).toHaveValue("temp");

    await user.click(screen.getByRole("button", { name: "Test & Preview" }));
    await waitFor(() => expect(testFetch).toHaveBeenCalledTimes(1));
    expect(testFetch).toHaveBeenCalledWith({
      url: "https://example.com/data.json",
      format: "json",
      method: "GET",
      headers: [],
      body: undefined,
    });

    await user.click(screen.getByRole("button", { name: /add mapping/i }));
    const last = onChange.mock.calls.at(-1)?.[0] as { mappings: Record<string, unknown>[] };
    expect(last.mappings.at(-1)).toEqual({ variable: "", path: "", default: "" });
  });
});
