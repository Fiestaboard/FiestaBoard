"use client";

import { Box, Button, type DeviceModel, LedMatrixDisplay, type LedTransitionSpec, Stack, Text } from "@fiestaboard/ui";
import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { useReducedMotion } from "@/hooks/use-reduced-motion";
import { useTranslations } from "@/i18n/translations";

/** A deliberately small ordering demonstration, never a hardware command. */
function NativePreview({
  strategy,
  interval,
  size,
  replay,
  reduced,
}: {
  strategy: string;
  interval: number;
  size: number;
  replay: number;
  reduced: boolean;
}) {
  const t = useTranslations("displays.transition");
  const text = t("previewMessage").padEnd(24).slice(0, 24);
  const cols = 12;
  const cells = Array.from(text, (char, index) => ({ char, index }));
  const rank = (index: number) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    switch (strategy) {
      case "column":
        return col;
      case "reverse-column":
        return cols - col - 1;
      case "edges-to-center":
        return Math.min(col, cols - col - 1);
      case "row":
        return row;
      case "diagonal":
        return col + row;
      // Stable scatter keeps a replay's ordering understandable.
      case "random":
        return (index * 7) % 24;
      default:
        return 0;
    }
  };
  return (
    <Box
      key={replay}
      role="img"
      aria-label={t("previewLabel", { name: t("previewMessage") })}
      className="grid w-fit max-w-full grid-cols-12 gap-0.5 rounded-lg bg-black p-2"
      data-native-strategy={strategy}
    >
      {cells.map(({ char, index }) => (
        <Text
          as="span"
          key={index}
          aria-hidden="true"
          className="flex h-7 w-4 items-center justify-center rounded-sm bg-zinc-800 font-mono text-xs text-white sm:h-9 sm:w-6 sm:text-base"
          style={
            replay > 0 && !reduced && strategy !== "none"
              ? {
                  animation: "display-order-reveal 180ms both",
                  animationDelay: `${Math.floor(rank(index) / size) * interval}ms`,
                }
              : undefined
          }
        >
          {char === " " ? "\u00a0" : char}
        </Text>
      ))}
      <style>{`@keyframes display-order-reveal { from { opacity: .15; transform: rotateX(80deg); } to { opacity: 1; transform: rotateX(0); } }`}</style>
    </Box>
  );
}

export function TransitionPreview({
  value,
  model,
  spec,
  native,
  interval = 50,
  size = 1,
  cloud = false,
}: {
  value: string;
  model?: DeviceModel;
  spec?: LedTransitionSpec | "none";
  native?: boolean;
  interval?: number;
  size?: number;
  cloud?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const reduced = useReducedMotion();
  const [replay, setReplay] = useState(1);
  const [message, setMessage] = useState(t("previewAlternate"));
  // Start from a settled message, then demonstrate once. No repeating timer.
  useEffect(() => {
    const timer = window.setTimeout(() => setMessage(t("previewMessage")), 120);
    return () => window.clearTimeout(timer);
  }, [replay, t]);
  const plugin = value.startsWith("plugin:");
  if (plugin)
    return (
      <Text size="sm" tone="muted">
        {t("pluginPreviewUnavailable")}
      </Text>
    );
  if (!model && !native && value !== "none") return null;
  return (
    <Stack
      gap="2"
      className="min-w-0 w-full max-w-full rounded-lg border bg-muted/20 p-3"
      data-testid="transition-preview"
    >
      {model ? (
        <LedMatrixDisplay
          key={replay}
          model={model}
          size={2}
          glow={false}
          message={message}
          transition={reduced ? "none" : (spec ?? "none")}
        />
      ) : (
        <NativePreview
          strategy={cloud ? "none" : value}
          interval={interval}
          size={size}
          replay={replay}
          reduced={reduced}
        />
      )}
      <Box className="flex flex-wrap items-center justify-between gap-2">
        <Text size="xs" tone="muted" className="max-w-prose">
          {reduced ? t("reducedMotionNote") : cloud ? t("cloudPreviewNote") : !model ? t("nativePreviewNote") : null}
        </Text>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            // Remount with the alternate layout already settled: resetting a
            // mounted LED would animate backward and interrupt that animation.
            setMessage(t("previewAlternate"));
            setReplay((n) => n + 1);
          }}
          disabled={reduced}
        >
          <RotateCcw className="mr-1 size-3" aria-hidden="true" />
          {t("replay")}
        </Button>
      </Box>
    </Stack>
  );
}
