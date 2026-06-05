import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { VersionDisplay } from "./version-display";

const meta = {
  title: "Layout/VersionDisplay",
  component: VersionDisplay,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof VersionDisplay>;

export default meta;
type Story = StoryObj<typeof meta>;

const createQueryClient = (
  version: string,
  isDev: boolean = false,
  updateAvailable: boolean = false,
  latestVersion?: string,
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  client.setQueryData(["version"], {
    package_version: version,
    is_dev: isDev,
  });

  if (updateAvailable && latestVersion) {
    client.setQueryData(["update-check"], {
      update_available: true,
      latest_version: latestVersion,
    });
  }

  return client;
};

export const Production: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("2.1.42", false)}>
        <div className="p-4 border rounded-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Development: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("2.1.42", true)}>
        <div className="p-4 border rounded-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const UpdateAvailable: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("2.1.42", false, true, "2.2.0")}>
        <div className="p-4 border rounded-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const InFooter = () => (
  <QueryClientProvider client={createQueryClient("2.1.42", false)}>
    <div className="border-t px-6 py-4 flex items-center justify-between bg-background">
      <VersionDisplay />
      <button className="text-xs text-muted-foreground hover:text-foreground">Settings</button>
    </div>
  </QueryClientProvider>
);

export const InSidebar = () => (
  <QueryClientProvider client={createQueryClient("2.1.42", true, true, "2.2.0")}>
    <aside className="w-64 h-screen border-r bg-background flex flex-col">
      <div className="flex-1" />
      <div className="border-t px-6 py-4 flex items-center justify-between">
        <VersionDisplay />
        <button className="text-xs text-muted-foreground hover:text-foreground">Theme</button>
      </div>
    </aside>
  </QueryClientProvider>
);
