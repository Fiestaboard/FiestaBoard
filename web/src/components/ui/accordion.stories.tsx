import type { Meta, StoryObj } from "@storybook/react";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "./accordion";

const meta = {
  title: "UI/Accordion",
  component: Accordion,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Accordion>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    type: "single",
    collapsible: true,
    className: "w-[450px]",
    children: (
      <>
        <AccordionItem value="item-1">
          <AccordionTrigger>Is it accessible?</AccordionTrigger>
          <AccordionContent>
            Yes. It adheres to the WAI-ARIA design pattern.
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="item-2">
          <AccordionTrigger>Is it styled?</AccordionTrigger>
          <AccordionContent>
            Yes. It comes with default styles that match your theme.
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="item-3">
          <AccordionTrigger>Is it animated?</AccordionTrigger>
          <AccordionContent>
            Yes. It's animated by default with smooth transitions.
          </AccordionContent>
        </AccordionItem>
      </>
    ),
  },
};

export const Multiple = () => (
  <Accordion type="multiple" className="w-[450px]">
    <AccordionItem value="item-1">
      <AccordionTrigger>First Section</AccordionTrigger>
      <AccordionContent>
        Content for the first section. Multiple sections can be open simultaneously.
      </AccordionContent>
    </AccordionItem>
    <AccordionItem value="item-2">
      <AccordionTrigger>Second Section</AccordionTrigger>
      <AccordionContent>
        Content for the second section.
      </AccordionContent>
    </AccordionItem>
    <AccordionItem value="item-3">
      <AccordionTrigger>Third Section</AccordionTrigger>
      <AccordionContent>
        Content for the third section.
      </AccordionContent>
    </AccordionItem>
  </Accordion>
);

export const DefaultOpen = () => (
  <Accordion type="single" collapsible defaultValue="item-2" className="w-[450px]">
    <AccordionItem value="item-1">
      <AccordionTrigger>Closed by default</AccordionTrigger>
      <AccordionContent>
        This section is closed by default.
      </AccordionContent>
    </AccordionItem>
    <AccordionItem value="item-2">
      <AccordionTrigger>Open by default</AccordionTrigger>
      <AccordionContent>
        This section is open by default using defaultValue.
      </AccordionContent>
    </AccordionItem>
  </Accordion>
);

export const AllTypes = () => (
  <div className="space-y-8">
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Single (collapsible)</h3>
      <Accordion type="single" collapsible className="w-[450px]">
        <AccordionItem value="item-1">
          <AccordionTrigger>Section 1</AccordionTrigger>
          <AccordionContent>Only one section can be open at a time.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="item-2">
          <AccordionTrigger>Section 2</AccordionTrigger>
          <AccordionContent>Opening this closes the other section.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="item-3">
          <AccordionTrigger>Section 3</AccordionTrigger>
          <AccordionContent>Try clicking between sections.</AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Multiple</h3>
      <Accordion type="multiple" className="w-[450px]">
        <AccordionItem value="item-1">
          <AccordionTrigger>Section 1</AccordionTrigger>
          <AccordionContent>Multiple sections can be open simultaneously.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="item-2">
          <AccordionTrigger>Section 2</AccordionTrigger>
          <AccordionContent>This one can stay open while opening others.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="item-3">
          <AccordionTrigger>Section 3</AccordionTrigger>
          <AccordionContent>Try opening all three sections.</AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  </div>
);
