import type { Meta, StoryObj } from "@storybook/react";
import { NavigationSidebar } from "./navigation-sidebar";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: Infinity,
    },
  },
});

const meta = {
  title: "Layout/NavigationSidebar",
  component: NavigationSidebar,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <QueryClientProvider client={queryClient}>
        <div className="min-h-screen">
          <Story />
          <main className="lg:pl-64 p-8">
            <h1 className="text-3xl font-bold mb-4">Page Content</h1>
            <p className="text-muted-foreground">
              The sidebar shows on desktop (left side) and as a mobile menu on smaller screens.
              Click the menu icon on mobile to see the navigation drawer.
            </p>
          </main>
        </div>
      </QueryClientProvider>
    ),
  ],
} satisfies Meta<typeof NavigationSidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Desktop: Story = {
  parameters: {
    viewport: {
      defaultViewport: "desktop",
    },
  },
};

export const Mobile: Story = {
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
};

export const Tablet: Story = {
  parameters: {
    viewport: {
      defaultViewport: "tablet",
    },
  },
};

export const WithDarkMode: Story = {
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [
    (Story) => (
      <div className="dark">
        <Story />
      </div>
    ),
  ],
};
