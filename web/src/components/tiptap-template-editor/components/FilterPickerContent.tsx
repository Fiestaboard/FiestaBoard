/**
 * Filter Picker Content - Filter options for toolbar
 * Can apply filters to selected variables or insert filter text
 */
"use client";

import { Badge } from "@fiestaboard/ui";
import type { Editor } from "@tiptap/react";
import { AlertCircle } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

interface FilterPickerContentProps {
  filters: string[];
  editor: Editor | null;
  onInsert?: (filter: string) => void;
}

export function FilterPickerContent({ filters, editor, onInsert }: FilterPickerContentProps) {
  const t = useTranslations("filterPicker");
  if (filters.length === 0) {
    return <div className="p-3 text-sm text-muted-foreground">{t("noFiltersAvailable")}</div>;
  }

  const handleFilterClick = (filterName: string) => {
    if (!editor) {
      onInsert?.(`|${filterName}`);
      return;
    }

    const { state } = editor;
    const { selection } = state;
    const { $from } = selection;

    // Check if selection is inside or on a variable node
    let variableNode = null;
    let variablePos = null;

    // Walk up the node tree to find if we're inside a variable node
    let depth = $from.depth;
    while (depth > 0) {
      const node = $from.node(depth);
      if (node.type.name === "variable") {
        variableNode = node;
        variablePos = $from.before(depth);
        break;
      }
      depth--;
    }

    // Also check if selection spans a variable node
    if (!variableNode) {
      state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
        if (node.type.name === "variable") {
          variableNode = node;
          variablePos = pos;
          return false; // Stop searching
        }
      });
    }

    if (variableNode && variablePos !== null) {
      // Apply filter to the selected variable
      const currentFilters = variableNode.attrs.filters || [];
      const filterNameOnly = filterName.split(":")[0]; // Extract name from "pad:3"

      // Check if filter already exists
      const filterExists = currentFilters.some((f: { name: string }) => f.name === filterNameOnly);

      if (!filterExists) {
        // Parse filter (handle pad:3, truncate:5, etc.)
        const filterParts = filterName.split(":");
        const newFilter = {
          name: filterParts[0],
          arg: filterParts[1] || undefined,
        };

        const updatedFilters = [...currentFilters, newFilter];

        // Update the variable node with the new filter
        const tr = state.tr;
        tr.setNodeMarkup(variablePos, undefined, {
          ...variableNode.attrs,
          filters: updatedFilters,
        });
        editor.view.dispatch(tr);
        editor.chain().focus().run();
      }
    } else if (filterName === "wrap" && selection.from !== selection.to) {
      // For wrap filter, if text is selected, wrap it in a wrappedText node
      const selectedText = state.doc.textBetween(selection.from, selection.to);

      if (selectedText.trim().length > 0) {
        // Check if selection is already inside a wrappedText node
        let isInWrappedText = false;
        depth = $from.depth;
        while (depth > 0) {
          const node = $from.node(depth);
          if (node.type.name === "wrappedText") {
            isInWrappedText = true;
            break;
          }
          depth--;
        }

        if (!isInWrappedText) {
          // Replace selection with wrappedText node
          editor
            .chain()
            .focus()
            .deleteSelection()
            .insertContent({
              type: "wrappedText",
              attrs: {
                text: selectedText,
              },
            })
            .run();
        }
      } else {
        onInsert?.(`|${filterName}`);
      }
    } else {
      // No variable selected, just insert the filter text
      onInsert?.(`|${filterName}`);
    }
  };

  // Check if a variable is currently selected or cursor is on a variable
  const hasVariableSelected = editor
    ? (() => {
        const { state } = editor;
        const { selection } = state;
        const { $from } = selection;

        // Walk up the node tree to find if we're inside a variable node
        let depth = $from.depth;
        while (depth > 0) {
          const node = $from.node(depth);
          if (node.type.name === "variable") {
            return true;
          }
          depth--;
        }

        // Check if selection spans a variable node
        let found = false;
        state.doc.nodesBetween(selection.from, selection.to, (node) => {
          if (node.type.name === "variable") {
            found = true;
            return false;
          }
        });
        return found;
      })()
    : false;

  return (
    <div className="p-2 min-w-[250px]">
      {!hasVariableSelected && editor && (
        <div className="mb-2 p-2 bg-muted/50 rounded-md text-xs text-muted-foreground flex items-start gap-2">
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <span>{t("selectVariableFirst")}</span>
        </div>
      )}
      <div className="space-y-2">
        {filters.map((filter) => {
          const filterName = filter.split(":")[0];
          return (
            <button
              key={filter}
              type="button"
              onClick={() => handleFilterClick(filter)}
              className={cn(
                "w-full text-left px-3 py-2 rounded-md text-sm",
                "hover:bg-accent hover:text-accent-foreground transition-colors",
                "flex items-center gap-2",
              )}
            >
              <Badge variant="secondary" className="font-mono text-xs">
                |{filter}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {filterName === "wrap" && t("filterDescWrap")}
                {filterName === "pad" && t("filterDescPad")}
                {filterName === "truncate" && t("filterDescTruncate")}
              </span>
            </button>
          );
        })}
      </div>
      <div className="mt-3 pt-3 border-t text-xs text-muted-foreground space-y-1">
        <p>Example: {"{{weather.temperature|pad:3}}"}</p>
        <p className="text-[10px]">
          <strong>|wrap</strong>: {t("wrapInstruction")}
        </p>
      </div>
    </div>
  );
}
