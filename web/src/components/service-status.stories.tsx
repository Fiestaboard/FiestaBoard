import type { Meta, StoryObj } from "@storybook/react";
import { ServiceStatus } from "./service-status";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const meta = {
  title: "Layout/ServiceStatus",
  component: ServiceStatus,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ServiceStatus>;

export default meta;
type Story = StoryObj<typeof meta>;

const createQueryClient = (running: boolean | null, error: boolean = false) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  
  if (!error && running !== null) {
    client.setQueryData(["status"], { running });
  }
  
  return client;
};

export const Running: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(true)}>
        <div className="flex items-center gap-3 p-4 border rounded-lg">
          <Story />
          <span className="text-sm text-muted-foreground">Service connected</span>
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Stopped: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(false)}>
        <div className="flex items-center gap-3 p-4 border rounded-lg">
          <Story />
          <span className="text-sm text-muted-foreground">Service stopped</span>
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Disconnected: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(null, true)}>
        <div className="flex items-center gap-3 p-4 border rounded-lg">
          <Story />
          <span className="text-sm text-muted-foreground">Connection error</span>
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Loading: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <div className="flex items-center gap-3 p-4 border rounded-lg">
          <Story />
          <span className="text-sm text-muted-foreground">Checking status...</span>
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const InHeader = () => (
  <QueryClientProvider client={createQueryClient(true)}>
    <header className="border-b bg-background px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold">FiestaBoard</h1>
        <ServiceStatus />
      </div>
      <div className="text-xs text-muted-foreground">v2.1.42</div>
    </header>
  </QueryClientProvider>
);
