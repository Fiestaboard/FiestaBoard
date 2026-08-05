import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@fiestaboard/ui";
import BoardScreenshot from "@site/src/components/BoardScreenshot";
import ThemedScreenshot from "@site/src/components/ThemedScreenshot";
import MDXComponents from "@theme-original/MDXComponents";

/**
 * Render Markdown tables with the FiestaUI `Table` component set so docs tables
 * match the design system (the handoff calls for the DS Table set in
 * production). The six GFM table elements map 1:1 onto FiestaUI's primitives;
 * GFM column-alignment `style` attributes pass through via prop spreading.
 */
export default {
  ...MDXComponents,
  ThemedScreenshot,
  BoardScreenshot,
  table: Table,
  thead: TableHeader,
  tbody: TableBody,
  tr: TableRow,
  th: TableHead,
  td: TableCell,
};
