import type { Meta, StoryObj } from "@storybook/react";
import { Toaster } from "./sonner";
import { Button } from "./button";
import { toast } from "sonner";

const meta = {
  title: "UI/Sonner",
  component: Toaster,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Toaster>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <>
      <Toaster />
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground mb-4">
          Click buttons to show toast notifications
        </p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => toast.success("Changes saved successfully")}>
            Success Toast
          </Button>
          <Button onClick={() => toast.error("Failed to save changes")}>
            Error Toast
          </Button>
          <Button onClick={() => toast.info("This is an informational message")}>
            Info Toast
          </Button>
          <Button onClick={() => toast.warning("Please review your settings")}>
            Warning Toast
          </Button>
          <Button onClick={() => toast.loading("Saving changes...")}>
            Loading Toast
          </Button>
        </div>
      </div>
    </>
  ),
};

export const WithDescription: Story = {
  render: () => (
    <>
      <Toaster />
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground mb-4">
          Toasts with descriptions
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() =>
              toast.success("Plugin enabled", {
                description: "Weather plugin has been successfully enabled",
              })
            }
          >
            Success with Description
          </Button>
          <Button
            onClick={() =>
              toast.error("Connection failed", {
                description: "Unable to connect to the API server",
              })
            }
          >
            Error with Description
          </Button>
        </div>
      </div>
    </>
  ),
};

export const WithAction: Story = {
  render: () => (
    <>
      <Toaster />
      <Button
        onClick={() =>
          toast.success("Changes saved", {
            action: {
              label: "Undo",
              onClick: () => toast.info("Changes undone"),
            },
          })
        }
      >
        Toast with Action
      </Button>
    </>
  ),
};

export const DurationControl: Story = {
  render: () => (
    <>
      <Toaster />
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground mb-4">
          Control toast duration
        </p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => toast.success("Quick toast", { duration: 1000 })}>
            1 Second
          </Button>
          <Button onClick={() => toast.success("Normal toast", { duration: 3000 })}>
            3 Seconds
          </Button>
          <Button onClick={() => toast.success("Long toast", { duration: 10000 })}>
            10 Seconds
          </Button>
          <Button onClick={() => toast.success("Persistent", { duration: Infinity })}>
            Persistent (dismiss manually)
          </Button>
        </div>
      </div>
    </>
  ),
};

export const MultipleToasts: Story = {
  render: () => (
    <>
      <Toaster />
      <Button
        onClick={() => {
          toast.success("First notification");
          setTimeout(() => toast.info("Second notification"), 200);
          setTimeout(() => toast.warning("Third notification"), 400);
        }}
      >
        Show Multiple Toasts
      </Button>
    </>
  ),
};

export const AllTypes = () => (
  <>
    <Toaster />
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">All Toast Types</h3>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="outline" onClick={() => toast.success("Operation completed")}>
          Success
        </Button>
        <Button variant="outline" onClick={() => toast.error("Operation failed")}>
          Error
        </Button>
        <Button variant="outline" onClick={() => toast.info("Did you know?")}>
          Info
        </Button>
        <Button variant="outline" onClick={() => toast.warning("Please be careful")}>
          Warning
        </Button>
        <Button variant="outline" onClick={() => toast.loading("Processing...")}>
          Loading
        </Button>
        <Button
          variant="outline"
          onClick={() => toast("Default notification", { description: "This is a basic toast" })}
        >
          Default
        </Button>
      </div>
    </div>
  </>
);
