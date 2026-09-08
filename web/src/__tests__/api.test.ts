import { beforeEach, describe, expect, it } from "vitest";

import type { PageCreate, RowConfig } from "@/lib/api";
import { api } from "@/lib/api";

import { requestStore } from "./mocks/handlers";

// Reset request store before each test
beforeEach(() => {
  requestStore.lastPageCreate = undefined;
  requestStore.lastTransitionUpdate = undefined;
  requestStore.lastOutputUpdate = undefined;
});

describe("API Contract Tests", () => {
  describe("Page API", () => {
    it("createPage with single type sends correct structure", async () => {
      const page: PageCreate = {
        name: "Weather Display",
        type: "single",
        display_type: "weather",
        duration_seconds: 300,
      };

      const result = await api.createPage(page);

      // 201 with the bare page since the Phase 2 conventions pass.
      expect(result.id).toBeDefined();
      expect(requestStore.lastPageCreate).toEqual(page);
      expect(requestStore.lastPageCreate?.type).toBe("single");
      expect(requestStore.lastPageCreate?.display_type).toBe("weather");
    });

    it("createPage with composite type sends row config", async () => {
      const rows: RowConfig[] = [
        { source: "weather", row_index: 0, target_row: 0 },
        { source: "weather", row_index: 1, target_row: 1 },
        { source: "datetime", row_index: 0, target_row: 2 },
      ];

      const page: PageCreate = {
        name: "Composite Display",
        type: "composite",
        rows,
        duration_seconds: 180,
      };

      const result = await api.createPage(page);

      expect(result.id).toBeDefined();
      expect(requestStore.lastPageCreate).toEqual(page);
      expect(requestStore.lastPageCreate?.type).toBe("composite");
      expect(requestStore.lastPageCreate?.rows).toHaveLength(3);

      // Verify row structure
      const firstRow = requestStore.lastPageCreate?.rows?.[0];
      expect(firstRow?.source).toBe("weather");
      expect(firstRow?.row_index).toBe(0);
      expect(firstRow?.target_row).toBe(0);
    });

    it("createPage with template type sends template lines", async () => {
      const page: PageCreate = {
        name: "Custom Template",
        type: "template",
        template: ["{{weather.temperature}}", "{{datetime.time}}", "{{red}}Alert{{/}}", "", "", "Line 6"],
        duration_seconds: 60,
      };

      const result = await api.createPage(page);

      expect(result.id).toBeDefined();
      expect(requestStore.lastPageCreate?.type).toBe("template");
      expect(requestStore.lastPageCreate?.template).toHaveLength(6);
      expect(requestStore.lastPageCreate?.template?.[0]).toBe("{{weather.temperature}}");
    });

    it("getPages returns correct structure", async () => {
      const result = await api.getPages();

      expect(result.pages).toBeDefined();
      expect(Array.isArray(result.pages)).toBe(true);
      expect(result.total).toBeGreaterThanOrEqual(0);

      // Check page structure
      if (result.pages.length > 0) {
        const page = result.pages[0];
        expect(page.id).toBeDefined();
        expect(page.name).toBeDefined();
        expect(page.type).toBeDefined();
      }
    });

    it("previewPage returns preview structure", async () => {
      const result = await api.previewPage("page-1");

      expect(result.page_id).toBe("page-1");
      expect(result.message).toBeDefined();
      expect(Array.isArray(result.lines)).toBe(true);
      expect(result.display_type).toBeDefined();
    });
  });

  describe("Settings API", () => {
    it("updateTransitionSettings sends correct structure", async () => {
      const settings = {
        strategy: "column",
        step_interval_ms: 100,
        step_size: 2,
      };

      const result = await api.updateTransitionSettings(settings);

      // Bare TransitionSettings since the conventions pass (Phase 2, Task 8).
      expect(result.strategy).toBe("column");
      expect(requestStore.lastTransitionUpdate).toEqual(settings);
    });

    it("updateTransitionSettings with null values for reset", async () => {
      const settings = {
        strategy: null,
        step_interval_ms: null,
        step_size: null,
      };

      const result = await api.updateTransitionSettings(settings);

      expect(result.strategy).toBeNull();
      expect(requestStore.lastTransitionUpdate?.strategy).toBeNull();
      expect(requestStore.lastTransitionUpdate?.step_interval_ms).toBeNull();
    });

    it("updateOutputSettings sends target correctly", async () => {
      const result = await api.updateOutputSettings("both");

      // Bare OutputSettings since the conventions pass (Phase 2, Task 8).
      expect(result.target).toBe("both");
      expect(requestStore.lastOutputUpdate?.target).toBe("both");
    });

    it("getTransitionSettings returns strategies list", async () => {
      const result = await api.getTransitionSettings();

      expect(result.strategy).toBeDefined();
      expect(result.available_strategies).toBeDefined();
      expect(Array.isArray(result.available_strategies)).toBe(true);
    });

    it("getOutputSettings returns available targets", async () => {
      const result = await api.getOutputSettings();

      expect(result.target).toBeDefined();
      expect(result.available_targets).toBeDefined();
      expect(Array.isArray(result.available_targets)).toBe(true);
      expect(result.available_targets).toContain("ui");
      expect(result.available_targets).toContain("board");
      expect(result.available_targets).toContain("both");
    });
  });

  describe("Template API", () => {
    it("getTemplateVariables returns all metadata", async () => {
      const result = await api.getTemplateVariables();

      expect(result.variables).toBeDefined();
      expect(result.colors).toBeDefined();
      expect(result.symbols).toBeDefined();
      expect(result.filters).toBeDefined();
      expect(result.syntax_examples).toBeDefined();

      // Check specific values
      expect(result.colors.red).toBe(63);
      expect(Array.isArray(result.symbols)).toBe(true);
    });

    it("validateTemplate returns validation result", async () => {
      const result = await api.validateTemplate("{{weather.temperature}}");

      expect(typeof result.valid).toBe("boolean");
      expect(Array.isArray(result.errors)).toBe(true);
    });

    it("renderTemplate returns rendered output", async () => {
      const result = await api.renderTemplate(["Line 1", "Line 2"]);

      expect(result.rendered).toBeDefined();
      expect(Array.isArray(result.lines)).toBe(true);
      expect(typeof result.line_count).toBe("number");
    });
  });

  describe("Display API", () => {
    it("getDisplayRaw returns raw data", async () => {
      const result = await api.getDisplayRaw("weather");

      expect(result.display_type).toBe("weather");
      expect(result.data).toBeDefined();
      expect(typeof result.available).toBe("boolean");
    });
  });
});
