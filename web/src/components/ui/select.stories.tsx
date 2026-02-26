import type { Meta, StoryObj } from "@storybook/react";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "./select";

const meta = {
  title: "UI/Select",
  component: Select,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: (
      <>
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder="Select a fruit" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="apple">Apple</SelectItem>
          <SelectItem value="banana">Banana</SelectItem>
          <SelectItem value="cherry">Cherry</SelectItem>
          <SelectItem value="grape">Grape</SelectItem>
          <SelectItem value="orange">Orange</SelectItem>
        </SelectContent>
      </>
    ),
  },
};

export const WithGroups = () => (
  <Select>
    <SelectTrigger className="w-[280px]">
      <SelectValue placeholder="Select a timezone" />
    </SelectTrigger>
    <SelectContent>
      <SelectGroup>
        <SelectLabel>North America</SelectLabel>
        <SelectItem value="est">Eastern Standard Time (EST)</SelectItem>
        <SelectItem value="cst">Central Standard Time (CST)</SelectItem>
        <SelectItem value="mst">Mountain Standard Time (MST)</SelectItem>
        <SelectItem value="pst">Pacific Standard Time (PST)</SelectItem>
      </SelectGroup>
      <SelectSeparator />
      <SelectGroup>
        <SelectLabel>Europe</SelectLabel>
        <SelectItem value="gmt">Greenwich Mean Time (GMT)</SelectItem>
        <SelectItem value="cet">Central European Time (CET)</SelectItem>
        <SelectItem value="eet">Eastern European Time (EET)</SelectItem>
      </SelectGroup>
    </SelectContent>
  </Select>
);

export const Disabled = () => (
  <Select disabled>
    <SelectTrigger className="w-[180px]">
      <SelectValue placeholder="Disabled" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem value="option">Option</SelectItem>
    </SelectContent>
  </Select>
);

export const WithDefaultValue = () => (
  <Select defaultValue="banana">
    <SelectTrigger className="w-[180px]">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem value="apple">Apple</SelectItem>
      <SelectItem value="banana">Banana</SelectItem>
      <SelectItem value="cherry">Cherry</SelectItem>
    </SelectContent>
  </Select>
);

export const AllStates = () => (
  <div className="space-y-6 w-[280px]">
    <div>
      <h3 className="text-sm font-medium mb-3">Default State</h3>
      <Select>
        <SelectTrigger>
          <SelectValue placeholder="Select an option..." />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1">Option 1</SelectItem>
          <SelectItem value="2">Option 2</SelectItem>
          <SelectItem value="3">Option 3</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">With Value Selected</h3>
      <Select defaultValue="2">
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1">Option 1</SelectItem>
          <SelectItem value="2">Option 2</SelectItem>
          <SelectItem value="3">Option 3</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">Disabled</h3>
      <Select disabled>
        <SelectTrigger>
          <SelectValue placeholder="Disabled select" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="1">Option 1</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">With Groups</h3>
      <Select defaultValue="pst">
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>US Timezones</SelectLabel>
            <SelectItem value="est">EST</SelectItem>
            <SelectItem value="pst">PST</SelectItem>
          </SelectGroup>
          <SelectSeparator />
          <SelectGroup>
            <SelectLabel>Europe</SelectLabel>
            <SelectItem value="gmt">GMT</SelectItem>
            <SelectItem value="cet">CET</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
  </div>
);
