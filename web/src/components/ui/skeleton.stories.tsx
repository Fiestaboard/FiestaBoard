import type { Meta, StoryObj } from "@storybook/react";

import { Skeleton } from "./skeleton";

const meta = {
  title: "UI/Skeleton",
  component: Skeleton,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    className: "w-[200px] h-[20px]",
  },
};

export const Circle: Story = {
  args: {
    className: "h-12 w-12 rounded-full",
  },
};

export const Card = () => (
  <div className="flex flex-col space-y-3 w-[250px]">
    <Skeleton className="h-[125px] w-[250px] rounded-xl" />
    <div className="space-y-2">
      <Skeleton className="h-4 w-[250px]" />
      <Skeleton className="h-4 w-[200px]" />
    </div>
  </div>
);

export const ProfileCard = () => (
  <div className="flex items-center space-x-4">
    <Skeleton className="h-12 w-12 rounded-full" />
    <div className="space-y-2">
      <Skeleton className="h-4 w-[250px]" />
      <Skeleton className="h-4 w-[200px]" />
    </div>
  </div>
);

export const TableRows = () => (
  <div className="space-y-4 w-[400px]">
    {Array.from({ length: 5 }).map((_, i) => (
      <div key={i} className="flex items-center space-x-4">
        <Skeleton className="h-4 w-4" />
        <Skeleton className="h-4 flex-1" />
        <Skeleton className="h-4 w-[100px]" />
      </div>
    ))}
  </div>
);

export const AllShapes = () => (
  <div className="space-y-6">
    <div>
      <h3 className="text-sm font-medium mb-3">Text Lines</h3>
      <div className="space-y-2 w-[400px]">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">Shapes</h3>
      <div className="flex flex-wrap gap-4">
        <Skeleton className="h-20 w-20" />
        <Skeleton className="h-20 w-20 rounded-full" />
        <Skeleton className="h-20 w-32 rounded-xl" />
        <Skeleton className="h-12 w-12 rounded-md" />
      </div>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">Common Patterns</h3>
      <div className="space-y-4 w-[400px]">
        <div className="flex items-center space-x-4">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="space-y-2 flex-1">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
        <div className="space-y-2">
          <Skeleton className="h-32 w-full rounded-lg" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    </div>
  </div>
);
