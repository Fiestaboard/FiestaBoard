import { describe, expect, it } from "vitest";

import { selectLibraryPages } from "@/lib/page-library-query";

const query = (text = "") => ({ text, sort: "name-asc" as const });
const ids = (pages: { id: string }[]) => pages.map((page) => page.id);

describe("saved page library queries", () => {
  it("matches all words across a page name and its saved template without evaluating it", () => {
    const pages = [
      { id: "one", name: "Morning", template: ["{{weather.temperature}}"] },
      { id: "two", name: "Morning", template: ["{{stocks.price}}"] },
    ];
    expect(ids(selectLibraryPages(pages, query(" MORNING weather ")))).toEqual(["one"]);
    expect(selectLibraryPages(pages, query("72 degrees"))).toEqual([]);
  });

  it("finds single-page and composite plugin sources", () => {
    const pages = [
      { id: "one", name: "A", display_type: "metro_arrivals" },
      { id: "two", name: "B", rows: [{ source: "metro_arrivals", row_index: 0, target_row: 0 }] },
      { id: "three", name: "C", display_type: "weather" },
    ];
    expect(ids(selectLibraryPages(pages, query("metro_arrivals")))).toEqual(["one", "two"]);
  });

  it("finds Canvas text, sources and bindings without indexing pixel or style literals", () => {
    const pages = [
      {
        id: "art",
        name: "Art",
        canvases: [
          {
            source: "{{plugin.canvas}}",
            content: {
              background: "#ff0000",
              pixels: ["PRIVATEPIXELS"],
              shapes: [{ type: "text", text: "Train arriving", x: "{{transit.offset}}", color: "#00ff00" }],
            },
          },
        ],
      },
    ];
    for (const text of ["plugin.canvas", "train", "transit.offset"]) {
      expect(ids(selectLibraryPages(pages, query(text)))).toEqual(["art"]);
    }
    for (const text of ["PRIVATEPIXELS", "ff0000", "00ff00"]) {
      expect(selectLibraryPages(pages, query(text))).toEqual([]);
    }
  });

  it("finds gradient and individual polygon-coordinate bindings", () => {
    const pages = [
      {
        id: "art",
        name: "Art",
        canvases: [
          {
            content: {
              shapes: [
                { type: "gradient", from: "{{sunrise.color}}", to: "{{sunset.color}}", angle: "{{wind.direction}}" },
                {
                  type: "polygon",
                  points: [
                    ["{{chart.start}}", 0],
                    [0, 1],
                    [1, 0],
                  ],
                },
              ],
            },
          },
        ],
      },
    ];
    for (const text of ["sunrise.color", "sunset.color", "wind.direction", "chart.start"]) {
      expect(ids(selectLibraryPages(pages, query(text)))).toEqual(["art"]);
    }
  });

  it("reads declared flexible text and Canvas blocks without treating opaque extensions as content", () => {
    const pages = [
      {
        id: "flex",
        name: "Flexible",
        blocks: [
          { kind: "text", text: "Next {{rail.departure}}", if: "{{rail.available}}" },
          {
            kind: "canvas",
            canvas: { source: "{{weather.icon}}", content: { shapes: [{ type: "text", text: "Hello" }] } },
          },
          { kind: "future", text: "OPAQUEBLOCK" },
        ],
        extension: { text: "OPAQUEEXTENSION" },
      },
    ];
    for (const text of ["rail.departure", "rail.available", "weather.icon", "hello"]) {
      expect(ids(selectLibraryPages(pages, query(text)))).toEqual(["flex"]);
    }
    for (const text of ["OPAQUEBLOCK", "OPAQUEEXTENSION"]) {
      expect(selectLibraryPages(pages, query(text))).toEqual([]);
    }
  });

  it("normalizes Unicode and treats punctuation as literal search text", () => {
    const pages = [{ id: "one", name: "Cafe\u0301 [special]", template: ["a+b"] }];
    expect(ids(selectLibraryPages(pages, query("CAFÉ [special] a+b")))).toEqual(["one"]);
    expect(selectLibraryPages(pages, query(".*"))).toEqual([]);
  });

  it("ignores malformed optional content and returns empty results safely", () => {
    const pages = [{ id: "one", name: "A", template: null, rows: [null], canvases: 5, blocks: [false] }];
    expect(selectLibraryPages(pages, query("missing"))).toEqual([]);
    expect(selectLibraryPages([], query())).toEqual([]);
  });

  const dates = [
    { id: "b", name: "Beta", created_at: "2024-01-02T00:00:00Z", updated_at: null },
    { id: "a", name: "alpha", created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-03T00:00:00Z" },
    { id: "c", name: "Gamma", created_at: "2024-01-03T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
    { id: "unknown", name: "Unknown", created_at: "invalid", updated_at: "invalid" },
  ];
  it.each([
    ["name-asc", ["a", "b", "c", "unknown"]],
    ["name-desc", ["unknown", "c", "b", "a"]],
    ["created-desc", ["c", "b", "a", "unknown"]],
    ["created-asc", ["a", "b", "c", "unknown"]],
    ["updated-desc", ["a", "b", "c", "unknown"]],
    ["updated-asc", ["c", "b", "a", "unknown"]],
  ] as const)("orders %s with unknown dates last and creation fallback for never-edited pages", (sort, expected) => {
    expect(ids(selectLibraryPages(dates, { text: "", sort }))).toEqual(expected);
  });

  it("breaks date/name ties by id without changing the input array or page objects", () => {
    const pages = Object.freeze([
      Object.freeze({ id: "b", name: "Same", created_at: "2024-01-01T00:00:00Z" }),
      Object.freeze({ id: "a", name: "same", created_at: "2024-01-01T00:00:00Z" }),
    ]);
    const result = selectLibraryPages(pages, { text: "", sort: "created-desc" });
    expect(ids(result)).toEqual(["a", "b"]);
    expect(result[0]).toBe(pages[1]);
    expect(pages.map((page) => page.id)).toEqual(["b", "a"]);
  });

  it.each([
    ["en", "name-asc", ["umlaut", "ring", "o", "z"]],
    ["en", "name-desc", ["z", "o", "ring", "umlaut"]],
    ["sv", "name-asc", ["z", "ring", "umlaut", "o"]],
    ["sv", "name-desc", ["o", "umlaut", "ring", "z"]],
  ] as const)("sorts %s %s by the selected locale's alphabet", (locale, sort, expected) => {
    const pages = [
      { id: "z", name: "Zebra" },
      { id: "umlaut", name: "Ärende" },
      { id: "ring", name: "Åsa" },
      { id: "o", name: "Öl" },
    ];
    expect(ids(selectLibraryPages(pages, { text: "", sort }, locale))).toEqual(expected);
  });
});
