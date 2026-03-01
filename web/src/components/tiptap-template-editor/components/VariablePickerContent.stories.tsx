import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VariablePickerContent } from "./VariablePickerContent";
import type { TemplateVariables, PluginManifest } from "@/lib/api";

const mockTemplateVariables: TemplateVariables = {
  variables: {
    weather: [
      "temperature",
      "condition",
      "location",
      "humidity",
      "wind_speed",
      "feels_like",
      "uv_index",
      "pressure",
      "visibility",
      "dew_point",
      "cloud_cover",
    ],
    datetime: ["time", "date", "day"],
    stocks: ["price", "change", "change_percent", "symbol", "name"],
    muni: [
      "stops.0.name",
      "stops.0.stop_code",
      "stops.0.all_lines.formatted",
      "stops.0.all_lines.next_arrival",
    ],
  },
  max_lengths: {
    "weather.temperature": 3,
    "weather.condition": 12,
    "weather.location": 15,
    "datetime.time": 5,
    "datetime.date": 10,
    "datetime.day": 2,
    "stocks.price": 8,
  },
  colors: {
    red: 63,
    orange: 64,
    yellow: 65,
    green: 66,
    blue: 67,
    violet: 68,
    white: 69,
    black: 70,
  },
  symbols: ["sun", "cloud", "rain", "star", "heart"],
  filters: ["pad:N", "truncate:N", "wrap"],
  formatting: {
    fill_space: {
      syntax: "{{fill_space}}",
      description: "Expands to fill remaining space on the line.",
    },
  },
  syntax_examples: {
    variable: "{{weather.temperature}}",
    color_inline: "{{red}}Warning{{/}}",
  },
};

const mockWeatherManifest: PluginManifest = {
  id: "weather",
  name: "Weather",
  version: "1.0.0",
  description: "Current weather conditions",
  author: "FiestaBoard",
  icon: "cloud",
  category: "weather",
  settings_schema: {},
  variables: {
    simple: [
      "temperature",
      "condition",
      "location",
      "humidity",
      "wind_speed",
      "feels_like",
      "uv_index",
      "pressure",
      "visibility",
      "dew_point",
      "cloud_cover",
    ],
  },
  max_lengths: {
    temperature: 3,
    condition: 12,
    location: 15,
  },
};

const mockDatetimeManifest: PluginManifest = {
  id: "datetime",
  name: "Date & Time",
  version: "1.0.0",
  description: "Current date and time",
  author: "FiestaBoard",
  icon: "clock",
  category: "utility",
  settings_schema: {},
  variables: {
    simple: ["time", "date", "day"],
  },
  max_lengths: {
    time: 5,
    date: 10,
    day: 2,
  },
};

const mockStocksManifest: PluginManifest = {
  id: "stocks",
  name: "Stocks",
  version: "1.0.0",
  description: "Stock market data",
  author: "FiestaBoard",
  icon: "trending-up",
  category: "data",
  settings_schema: {},
  variables: {
    simple: ["price", "change", "change_percent", "symbol", "name"],
  },
  max_lengths: {
    price: 8,
    symbol: 5,
  },
};

const mockMuniManifest: PluginManifest = {
  id: "muni",
  name: "Muni Transit",
  version: "1.0.0",
  description: "SF Muni transit arrivals",
  author: "FiestaBoard",
  icon: "train-front",
  category: "transit",
  settings_schema: {},
  variables: {
    arrays: {
      stops: {
        label_field: "name",
        item_fields: ["name", "stop_code", "line", "destination_name"],
        sub_arrays: {
          lines: {
            key_type: "dynamic",
            key_field: "line",
            item_fields: ["next_arrival", "destination", "formatted"],
          },
        },
      },
    },
  },
  max_lengths: {},
};

const mockMuniDisplayData = {
  stops: [
    {
      name: "Market & 3rd St",
      stop_code: "15726",
      line: "N",
      destination_name: "Ocean Beach",
      all_lines: {
        formatted: "N-5m, K-8m",
        next_arrival: "5",
      },
      lines: {
        N: { next_arrival: "5", destination: "Ocean Beach", formatted: "5 min" },
        K: { next_arrival: "8", destination: "Balboa Park", formatted: "8 min" },
      },
    },
    {
      name: "Powell Station",
      stop_code: "15731",
      line: "F",
      destination_name: "Fishermans Wharf",
      all_lines: {
        formatted: "F-3m",
        next_arrival: "3",
      },
      lines: {
        F: {
          next_arrival: "3",
          destination: "Fishermans Wharf",
          formatted: "3 min",
        },
      },
    },
  ],
};

function createQueryClient(opts?: {
  variables?: TemplateVariables;
  manifests?: Record<string, PluginManifest>;
  displayData?: Record<string, { data: Record<string, unknown> }>;
}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });

  const variables = opts?.variables ?? mockTemplateVariables;
  client.setQueryData(["template-variables"], variables);

  const manifests = opts?.manifests ?? {
    weather: mockWeatherManifest,
    datetime: mockDatetimeManifest,
    stocks: mockStocksManifest,
    muni: mockMuniManifest,
  };
  for (const [id, manifest] of Object.entries(manifests)) {
    client.setQueryData(["plugin-manifest", id], manifest);
  }

  if (opts?.displayData) {
    const pluginIds = Object.keys(opts.displayData);
    client.setQueryData(["plugin-displays-batch", pluginIds], {
      displays: opts.displayData,
    });
  }

  return client;
}

const meta = {
  title: "Components/VariablePickerContent",
  component: VariablePickerContent,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof VariablePickerContent>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    onInsert: (variable: string) => console.log("Insert:", variable),
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient()}>
        <Story />
      </QueryClientProvider>
    ),
  ],
};

export const WithTransitData: Story = {
  args: {
    onInsert: (variable: string) => console.log("Insert:", variable),
  },
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient({
          displayData: {
            muni: { data: mockMuniDisplayData },
          },
        })}
      >
        <Story />
      </QueryClientProvider>
    ),
  ],
};

export const SingleCategory: Story = {
  args: {
    onInsert: (variable: string) => console.log("Insert:", variable),
  },
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient({
          variables: {
            variables: {
              weather: mockTemplateVariables.variables.weather,
            },
            max_lengths: mockTemplateVariables.max_lengths,
            colors: {},
            symbols: [],
            filters: [],
            formatting: {},
            syntax_examples: {},
          },
          manifests: { weather: mockWeatherManifest },
        })}
      >
        <Story />
      </QueryClientProvider>
    ),
  ],
};

export const NoVariables: Story = {
  args: {
    onInsert: (variable: string) => console.log("Insert:", variable),
  },
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient({
          variables: {
            variables: {},
            max_lengths: {},
            colors: {},
            symbols: [],
            filters: [],
            formatting: {},
            syntax_examples: {},
          },
          manifests: {},
        })}
      >
        <Story />
      </QueryClientProvider>
    ),
  ],
};

export const Loading: Story = {
  args: {
    onInsert: (variable: string) => console.log("Insert:", variable),
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <Story />
      </QueryClientProvider>
    ),
  ],
};
