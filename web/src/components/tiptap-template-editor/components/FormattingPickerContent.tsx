/**
 * Formatting Picker Content - Formatting options for toolbar
 */
"use client";

import {
  Badge,
  Box,
  Flex,
  Grid,
  Stack,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { ChevronRight, ChevronsLeftRight } from "lucide-react";
import React from "react";

import { useTranslations } from "@/i18n/translations";
import { FIESTABOARD_COLORS } from "@/lib/board-colors";
import { cn } from "@/lib/utils";

interface FormattingOption {
  name: string;
  syntax: string;
  description?: string;
}

interface FormattingPickerContentProps {
  formatting: Record<string, { syntax: string; description?: string }>;
  onInsert: (syntax: string) => void;
}

const COLOR_MAP: Record<string, { bg: string; needsDarkText: boolean }> = {
  red: { bg: FIESTABOARD_COLORS.red, needsDarkText: false },
  orange: { bg: FIESTABOARD_COLORS.orange, needsDarkText: false },
  yellow: { bg: FIESTABOARD_COLORS.yellow, needsDarkText: true },
  green: { bg: FIESTABOARD_COLORS.green, needsDarkText: true },
  blue: { bg: FIESTABOARD_COLORS.blue, needsDarkText: false },
  violet: { bg: FIESTABOARD_COLORS.violet, needsDarkText: false },
  white: { bg: FIESTABOARD_COLORS.white, needsDarkText: true },
  black: { bg: FIESTABOARD_COLORS.black, needsDarkText: false },
};

const COLOR_ORDER = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"] as const;

export function FormattingPickerContent({ formatting, onInsert }: FormattingPickerContentProps) {
  const t = useTranslations("formattingPicker");
  const [showRepeatColorPicker, setShowRepeatColorPicker] = React.useState(false);
  const [customChar, setCustomChar] = React.useState("");

  const options: FormattingOption[] = Object.entries(formatting).map(([name, info]) => ({
    name: name.replace(/_/g, " "),
    syntax: info.syntax,
    description: info.description,
  }));

  if (options.length === 0) {
    return (
      <Text tone="muted" className="p-3">
        {t("noFormattingAvailable")}
      </Text>
    );
  }

  const handleOptionClick = (option: FormattingOption) => {
    // Check if this is fill_space_repeat - show color picker
    if (option.syntax.includes("fill_space_repeat")) {
      setShowRepeatColorPicker(true);
    } else {
      onInsert(option.syntax);
    }
  };

  const handleColorSelect = (colorName: string) => {
    onInsert(`{{fill_space_repeat:${colorName}}}`);
    setShowRepeatColorPicker(false);
    setCustomChar("");
  };

  const handleCustomCharSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customChar) {
      handleColorSelect(customChar); // Reuse the same handler
    }
  };

  // Show color + custom picker for fill_space_repeat
  if (showRepeatColorPicker) {
    return (
      <TooltipProvider>
        <Box className="p-2 min-w-[240px] max-w-[280px]">
          <button
            type="button"
            onClick={() => setShowRepeatColorPicker(false)}
            className="text-xs text-muted-foreground hover:text-foreground mb-2 flex items-center gap-1"
          >
            {t("back")}
          </button>

          {/* Colors Section */}
          <Text size="xs" tone="muted" weight="medium" className="mb-2">
            {t("selectColor")}
          </Text>

          <Grid cols="4" gap="2" className="mb-3">
            {COLOR_ORDER.map((colorName) => {
              const colorInfo = COLOR_MAP[colorName];
              if (!colorInfo) return null;

              return (
                <Tooltip key={colorName}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => handleColorSelect(colorName)}
                      style={{ backgroundColor: colorInfo.bg }}
                      className={cn(
                        "h-10 rounded-md text-xs font-medium transition-all hover:scale-105 hover:shadow-md",
                        "flex items-center justify-center",
                        colorInfo.needsDarkText ? "text-black/80" : "text-white/90",
                      )}
                      aria-label={`${colorName} color`}
                    >
                      {colorName}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <Text>{colorName}</Text>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </Grid>

          {/* Custom String */}
          <Box className="pt-2 border-t border-border">
            <Text size="xs" tone="muted" className="mb-1.5">
              {t("orCustomPattern")}
            </Text>
            <Box as="form" onSubmit={handleCustomCharSubmit} className="flex gap-1.5">
              <input
                type="text"
                value={customChar}
                onChange={(e) => setCustomChar(e.target.value)}
                placeholder="e.g. - or =-"
                maxLength={10}
                className={cn(
                  "flex-1 px-2 py-1.5 text-sm font-mono rounded-md",
                  "border border-border bg-background",
                  "focus:outline-none focus:ring-2 focus:ring-ring",
                )}
              />
              <button
                type="submit"
                disabled={!customChar}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-medium",
                  "bg-primary text-primary-foreground",
                  "hover:bg-primary/90 transition-colors",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                {t("use")}
              </button>
            </Box>
          </Box>
        </Box>
      </TooltipProvider>
    );
  }

  // Show main formatting options
  return (
    <TooltipProvider>
      <Box className="p-1.5 min-w-[240px] max-w-[280px]">
        <Stack gap="0.5">
          {options.map((option) => {
            const isRepeat = option.syntax.includes("fill_space_repeat");

            return (
              <Tooltip key={option.syntax}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => handleOptionClick(option)}
                    className={cn(
                      "w-full text-left px-2.5 py-1.5 rounded-md text-sm",
                      "hover:bg-accent hover:text-accent-foreground transition-colors",
                      "flex items-center justify-between gap-2 group",
                    )}
                  >
                    <Flex align="center" gap="2" className="flex-1 min-w-0">
                      <ChevronsLeftRight className="w-3.5 h-3.5 text-muted-foreground group-hover:text-accent-foreground flex-shrink-0" />
                      <Text
                        as="span"
                        weight="medium"
                        className="capitalize truncate group-hover:text-accent-foreground"
                      >
                        {option.name}
                      </Text>
                    </Flex>
                    {isRepeat ? (
                      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground group-hover:text-accent-foreground flex-shrink-0" />
                    ) : (
                      <Badge variant="secondary" className="font-mono text-[10px] px-1.5 py-0 flex-shrink-0">
                        {option.syntax}
                      </Badge>
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{option.description ?? option.name}</Text>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </Stack>
      </Box>
    </TooltipProvider>
  );
}
