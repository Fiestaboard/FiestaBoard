/**
 * BB-B-19 (184:159319): the builder's template | preview grid and the Creator
 * IDE's console | inspector grid share one column template, so the Console
 * sits under the template and the Inspector under the preview.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, it } from "vitest";

const read = (file: string) => readFileSync(resolve(__dirname, "..", file), "utf8");

function lgColumns(source: string, marker: string): string {
  const at = source.indexOf(marker);
  expect(at).toBeGreaterThan(-1);
  const line = source.slice(source.lastIndexOf("className=", at), source.indexOf("\n", at));
  const match = /lg:grid-cols-(\S+?)["\s]/.exec(line);
  return match?.[1] ?? "";
}

it("lines the IDE's columns up with the builder's", () => {
  const builder = lgColumns(read("components/page-builder.tsx"), "grid min-w-0 grid-cols-1 lg:grid-cols-");
  const ide = lgColumns(read("components/ide/creator-ide.tsx"), "grid min-w-0 grid-cols-1 items-start");
  expect(builder).toBe("2");
  expect(ide).toBe(builder);
});
