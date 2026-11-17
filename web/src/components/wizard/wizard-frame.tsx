import { BoardBackdrop, Box, Card, FiestaLogo, Heading, Stack, Text, WizardProgress } from "@fiestaboard/ui";
import type { ReactNode } from "react";

const PHRASES = ["WELCOME", "LETS GET STARTED", "72 AND CLEAR", "GOOD MORNING", "BOARD CONNECTED", "HELLO WORLD"];

/** TODO(FiestaUI): WizardShell needs step 0, hub metadata and the 640/358
 * anatomy. Compose its published parts until the shell exposes those slots. */
export function WizardFrame({
  current,
  steps,
  title,
  description,
  hub,
  progressLabel,
  eyebrow,
  children,
  footer,
}: {
  current: number;
  steps: string[];
  title: string;
  description: string;
  hub: string;
  progressLabel: string;
  eyebrow?: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <Box className="fixed inset-0 z-50 w-screen overflow-y-auto bg-background" data-testid="setup-wizard">
      <Box className="hidden md:block">
        <BoardBackdrop phrases={PHRASES} fixed />
      </Box>
      <Box className="relative flex min-h-full items-start justify-center px-4 pb-6 pt-4 md:items-center md:p-8">
        <Card className="w-full max-w-[640px] gap-4 rounded-[var(--radius-card)] p-5 shadow-[var(--elevation-card)] md:gap-5 md:p-8">
          <Box as="header" className="flex min-h-25 flex-wrap items-center justify-between gap-2">
            <FiestaLogo size="sm" />
            <Text size="xs" tone="muted" className="break-all">
              {hub}
            </Text>
          </Box>
          {current > 0 && (
            <WizardProgress
              current={current}
              steps={steps}
              label={progressLabel}
              className="[&_li>span:last-child]:whitespace-normal [&_li>span:last-child]:break-words"
            />
          )}
          <Stack gap="3">
            {eyebrow && (
              <Text size="xs" weight="medium" className="text-brand">
                {eyebrow}
              </Text>
            )}
            <Heading level={1} size="xl" tabIndex={-1}>
              {title}
            </Heading>
            <Text size="sm" tone="muted">
              {description}
            </Text>
          </Stack>
          {children}
          {footer}
        </Card>
      </Box>
    </Box>
  );
}
