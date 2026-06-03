import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Label } from "@/components/ui/label";
import { PagePickerField } from "./page-picker-field";

const mockPages = {
  pages: [
    {
      id: "page-uuid-1",
      name: "Weather Dashboard",
      type: "template" as const,
      device_type: "flagship" as const,
      duration_seconds: 300,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "page-uuid-2",
      name: "Morning Briefing",
      type: "template" as const,
      device_type: "flagship" as const,
      duration_seconds: 300,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "page-uuid-3",
      name: "Static Welcome",
      type: "single" as const,
      device_type: "flagship" as const,
      duration_seconds: 300,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 3,
};

function withMockedPages(initialValue: string) {
  return function Wrapper() {
    const [value, setValue] = useState(initialValue);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity } },
    });
    queryClient.setQueryData(["pages"], mockPages);

    return (
      <QueryClientProvider client={queryClient}>
        <div className="max-w-md space-y-3">
          <div className="text-xs text-muted-foreground">
            Selected: <code>{value || "(none)"}</code>
          </div>
          {/* The Label is what gives the Radix Select trigger its accessible
              name; the SchemaForm renders one in production, so we mirror that
              here to keep the story representative and pass axe-core's
              button-name rule. */}
          <Label htmlFor="trigger_page_id">Trigger Page</Label>
          <PagePickerField
            id="trigger_page_id"
            value={value}
            onChange={(v) => setValue(String(v ?? ""))}
          />
        </div>
      </QueryClientProvider>
    );
  };
}

const meta = {
  title: "PluginSettings/PagePickerField",
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  render: withMockedPages(""),
};

export const PreSelected: Story = {
  render: withMockedPages("page-uuid-2"),
};
