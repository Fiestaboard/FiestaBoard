import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SchemaForm, type JSONSchema } from "@/components/plugin-settings";

/**
 * Regression tests for the bug reported in
 * "Remove Live Input Validation Logic" (FiestaBoard issue):
 *
 * When a numeric setting (e.g. Airport Latitude) had a `default` in its JSON
 * schema, the user could not delete the value: as soon as the input became
 * empty (or transiently invalid like "-" while editing a negative number),
 * the form re-rendered with the schema default and the user's edit was undone.
 * This made it impossible to clear/replace the default by typing or pasting.
 *
 * The fix has two parts:
 *  1. SchemaForm no longer substitutes `property.default` for the displayed
 *     value on every render.
 *  2. NumberField keeps a local text buffer and only commits / validates on
 *     blur, so transient editing states (empty, "-", "1.") don't get parsed
 *     into NaN/undefined and round-trip back as the previous value.
 */
describe("SchemaForm - editing fields with schema defaults", () => {
  function Harness({
    schema,
    initial,
  }: {
    schema: JSONSchema;
    initial: Record<string, unknown>;
  }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return <SchemaForm schema={schema} values={values} onChange={setValues} />;
  }

  const numberSchema: JSONSchema = {
    type: "object",
    properties: {
      latitude: {
        type: "number",
        title: "Airport Latitude",
        default: 37.6213,
      },
    },
  };

  it("allows the user to clear a numeric field that has a schema default", async () => {
    const user = userEvent.setup();
    render(<Harness schema={numberSchema} initial={{ latitude: 37.6213 }} />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;
    expect(input.value).toBe("37.6213");

    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");

    // Previously the field snapped back to the schema default (37.6213).
    expect(input.value).toBe("");
  });

  it("allows the user to replace a numeric default by typing a new value", async () => {
    const user = userEvent.setup();
    render(<Harness schema={numberSchema} initial={{ latitude: 37.6213 }} />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;

    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");
    await user.type(input, "40.7128");
    await user.tab();

    expect(input.value).toBe("40.7128");
  });

  it("does not snap back to the previous value while the user is mid-edit "
    + "in a negative number (e.g. deleting the digits of '-1')", async () => {
    const user = userEvent.setup();
    const negativeSchema: JSONSchema = {
      type: "object",
      properties: {
        latitude: {
          type: "number",
          title: "Airport Latitude",
          default: -1,
        },
      },
    };
    render(<Harness schema={negativeSchema} initial={{ latitude: -1 }} />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;
    expect(input.value).toBe("-1");

    // Delete the trailing digit; the field is now in an intermediate state
    // that is not yet a valid number. Previously this would snap back to -1.
    await user.click(input);
    await user.keyboard("{End}{Backspace}");

    expect(input.value).not.toBe("-1");

    // Finish typing a new value; the input should accept it cleanly.
    await user.type(input, "2");
    await user.tab();
    expect(input.value).toBe("-2");
  });

  it("treats an entirely-cleared numeric field as undefined on blur "
    + "(commit-on-blur)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    function ControlledHarness() {
      const [values, setValues] = useState<Record<string, unknown>>({ latitude: 37.6213 });
      return (
        <SchemaForm
          schema={numberSchema}
          values={values}
          onChange={(next) => {
            setValues(next);
            onChange(next);
          }}
        />
      );
    }
    render(<ControlledHarness />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;
    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");
    await user.tab();

    const lastCall = onChange.mock.calls.at(-1)?.[0] as Record<string, unknown> | undefined;
    expect(lastCall).toBeDefined();
    expect(lastCall!.latitude).toBeUndefined();
  });

  const stringSchema: JSONSchema = {
    type: "object",
    properties: {
      city: {
        type: "string",
        title: "City",
        default: "San Francisco",
      },
    },
  };

  it("allows the user to clear a string field that has a schema default", async () => {
    const user = userEvent.setup();
    render(<Harness schema={stringSchema} initial={{ city: "San Francisco" }} />);

    const input = screen.getByLabelText("City") as HTMLInputElement;
    expect(input.value).toBe("San Francisco");

    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");

    expect(input.value).toBe("");
  });
});
