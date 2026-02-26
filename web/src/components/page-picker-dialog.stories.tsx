import type { Meta, StoryObj } from "@storybook/react";
import { PagePickerDialog } from "./page-picker-dialog";
import { useState } from "react";

const meta = {
  title: "Forms/PagePickerDialog",
  component: PagePickerDialog,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    allowNone: {
      control: "boolean",
      description: "Allow selecting 'None' as an option",
    },
  },
} satisfies Meta<typeof PagePickerDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

const mockPages = [
  { id: "page-1", name: "Weather Dashboard" },
  { id: "page-2", name: "Transit Times" },
  { id: "page-3", name: "Morning Briefing" },
  { id: "page-4", name: "Evening Summary" },
];

const mockPagesWithTypes = [
  { id: "page-1", name: "Weather Dashboard", type: "flagship" },
  { id: "page-2", name: "Transit Times", type: "flagship" },
  { id: "page-3", name: "Quick Note", type: "note" },
  { id: "page-4", name: "Evening Summary", type: "flagship" },
];

export const Default: Story = {
  args: {
    pages: mockPages,
    selectedPageId: "page-1",
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: false,
  },
};

export const WithNoneOption: Story = {
  args: {
    pages: mockPages,
    selectedPageId: null,
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: true,
  },
};

export const WithPageTypes: Story = {
  args: {
    pages: mockPagesWithTypes,
    selectedPageId: "page-2",
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: false,
  },
};

export const NoSelection: Story = {
  args: {
    pages: mockPages,
    selectedPageId: null,
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: false,
  },
};

export const ManyPages: Story = {
  args: {
    pages: Array.from({ length: 15 }, (_, i) => ({
      id: `page-${i + 1}`,
      name: `Page ${i + 1}`,
      type: i % 3 === 0 ? "note" : "flagship",
    })),
    selectedPageId: "page-5",
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: true,
  },
};

export const EmptyState: Story = {
  args: {
    pages: [],
    selectedPageId: null,
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: true,
  },
};

export const Interactive = () => {
  const [selectedId, setSelectedId] = useState<string | null>("page-2");

  return (
    <div className="max-w-md space-y-4">
      <div className="text-sm text-muted-foreground">
        <strong>Selected page ID:</strong> {selectedId || "none"}
      </div>
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={selectedId}
        onSelect={setSelectedId}
        allowNone={true}
      />
    </div>
  );
};

export const InDialog = () => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(true);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 rounded-md bg-primary text-primary-foreground"
      >
        Open Dialog
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-background border rounded-lg shadow-lg">
        <div className="p-6 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Set Default Page</h2>
            <p className="text-sm text-muted-foreground mt-1">
              This page will display during schedule gaps
            </p>
          </div>
          
          <PagePickerDialog
            pages={mockPages}
            selectedPageId={selectedId}
            onSelect={setSelectedId}
            allowNone={true}
          />
          
          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={() => setIsOpen(false)}
              className="px-4 py-2 rounded-md border text-sm font-medium"
            >
              Cancel
            </button>
            <button
              onClick={() => {
                console.log("Saved:", selectedId);
                setIsOpen(false);
              }}
              className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
