import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import type { Collection } from "@/lib/api";

import { PagePickerDialog } from "./page-picker-dialog";

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
      <PagePickerDialog pages={mockPages} selectedPageId={selectedId} onSelect={setSelectedId} allowNone={true} />
    </div>
  );
};

const mockCollections: Collection[] = [
  {
    id: "collection:abc-123",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2", "page-3"],
    selection_mode: "time",
    time: { interval_seconds: 30 },
    variable: null,
    random: null,
    created_at: "2024-02-01T00:00:00Z",
  },
  {
    id: "collection:def-456",
    name: "Evening Loop",
    page_ids: ["page-3", "page-4"],
    selection_mode: "time",
    time: { interval_seconds: 60 },
    variable: null,
    random: null,
    created_at: "2024-02-02T00:00:00Z",
  },
];

export const WithCollections: Story = {
  args: {
    pages: mockPages,
    collections: mockCollections,
    selectedPageId: "page-1",
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: false,
  },
};

export const WithSelectedCollection: Story = {
  args: {
    pages: mockPages,
    collections: mockCollections,
    selectedPageId: "collection:abc-123",
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: false,
  },
};

export const WithCollectionsAndNone: Story = {
  args: {
    pages: mockPages,
    collections: mockCollections,
    selectedPageId: null,
    onSelect: (pageId: string | null) => console.log("Selected:", pageId),
    allowNone: true,
  },
};

export const InDialog = () => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(true);

  return (
    <>
      {!isOpen && <Button onClick={() => setIsOpen(true)}>Open Dialog</Button>}
      <AlertDialog open={isOpen} onOpenChange={setIsOpen}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Set Default Page</AlertDialogTitle>
            <AlertDialogDescription>This page will display during schedule gaps</AlertDialogDescription>
          </AlertDialogHeader>

          <PagePickerDialog pages={mockPages} selectedPageId={selectedId} onSelect={setSelectedId} allowNone={true} />

          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button
              onClick={() => {
                console.log("Saved:", selectedId);
                setIsOpen(false);
              }}
            >
              Save
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
