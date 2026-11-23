import { Box, CardDescription, CardTitle, Flex, PageCard, PageSection } from "@fiestaboard/ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * A single Settings panel, using the shared card surface and section spacing.
 *
 * The heading is drawn here rather than by `PageSection`, because 07e's
 * settings cards (`320:8881`, `333:56102`, `333:57132`) read a size down from
 * the section scale `PageSection` titles at: a 14/20 semibold title with no
 * glyph over a 12/16 description (BB-FC-1). `icon` is still accepted so call
 * sites need not change, and is deliberately not drawn.
 */
export function SettingsPanel({
  title,
  icon: _icon,
  description,
  action,
  children,
  className,
  contentClassName,
  ...props
}: ComponentProps<typeof PageSection>) {
  const hasHeading = title != null || description != null || action != null;
  return (
    <PageCard>
      <PageSection {...props} className={cn("p-5", className)}>
        {hasHeading && (
          <Flex align="start" justify="between" gap="4" className="mb-4" data-slot="settings-panel-heading">
            <Box className="min-w-0">
              {title != null && (
                <CardTitle size="base" className="text-sm leading-5">
                  {title}
                </CardTitle>
              )}
              {description != null && <CardDescription className="mt-1 text-xs">{description}</CardDescription>}
            </Box>
            {action}
          </Flex>
        )}
        {contentClassName ? <Box className={contentClassName}>{children}</Box> : children}
      </PageSection>
    </PageCard>
  );
}
