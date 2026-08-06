/**
 * Swizzled `@theme/Admonition/Types` — renders every `:::` admonition with the
 * FiestaUI `Alert` component instead of Infima's `.alert` boxes.
 *
 * Why swizzle `Types` rather than `Admonition` or `Admonition/Layout`:
 * `Types` is the single map of admonition type -> component, so replacing it
 * re-skins all six types (plus the legacy aliases) from one file while leaving
 * `@theme/Admonition` free to keep doing its `processAdmonitionProps` work
 * (MDX title extraction, unknown-type fallback). Swizzling `Layout` instead
 * would have left every type component still injecting Infima's
 * `alert alert--success` classes, which we would then have to strip back out.
 *
 * Behaviour deliberately preserved from upstream:
 *   - the `theme-admonition` / `theme-admonition-<type>` public class names,
 *     which user CSS and the docs search indexer may target
 *   - the `theme.admonition.*` translation ids for default titles
 *   - the legacy aliases (`secondary`, `important`, `success`, `caution`)
 *   - a caller-supplied `icon` prop overriding the per-type default
 *
 * Changed: icons come from lucide-react (what FiestaUI and the app itself use)
 * rather than Docusaurus's octicon set, and the title renders capitalised
 * instead of Infima's ALL-CAPS `text-transform`.
 */

import { ThemeClassNames } from "@docusaurus/theme-common";
import Translate from "@docusaurus/Translate";
import { Alert, AlertDescription, AlertTitle, cn } from "@fiestaboard/ui";
import type { Props } from "@theme/Admonition";
import type { LucideIcon } from "lucide-react";
import { Info, Lightbulb, NotepadText, OctagonAlert, TriangleAlert } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

type AlertVariant = "default" | "destructive" | "info" | "success" | "warning";

interface AdmonitionConfig {
  /** FiestaUI `Alert` variant supplying the border + title colour. */
  variant: AlertVariant;
  icon: LucideIcon;
  /** Default heading, shown when the author writes `:::tip` with no title. */
  defaultTitle: ReactNode;
}

/**
 * Build an admonition type component from its design-system configuration.
 *
 * `AlertDescription` is pinned back to `text-foreground` at body size: the
 * `info`/`success`/`warning`/`destructive` variants colour *all* their text,
 * which reads fine for a one-line app alert but is unreadable for a docs
 * callout carrying paragraphs, links, and code. The colour therefore lands on
 * the icon and title only, and the body stays at prose contrast and prose size.
 */
function createAdmonitionType({ variant, icon: Icon, defaultTitle }: AdmonitionConfig): ComponentType<Props> {
  return function AdmonitionType({ type, title, icon, className, children }: Props) {
    return (
      <Alert
        variant={variant}
        className={cn(
          ThemeClassNames.common.admonition,
          ThemeClassNames.common.admonitionType(type),
          "my-4",
          className,
        )}
      >
        {icon ?? <Icon className="size-4" aria-hidden="true" />}
        {/* `text-current` re-inherits the variant colour from `Alert`: `AlertTitle`
            renders an `h5`, and Infima's `h1-h6 { color: var(--ifm-heading-color) }`
            would otherwise beat the inherited `text-success`/`text-warning`/… */}
        {/* `first-letter:uppercase`, not `capitalize`: the default titles are
            lowercase words ("tip", "info") that need a capital, but author-written
            titles must survive intact — `capitalize` would title-case every word
            and turn "Don't have a Pi yet?" into "Don't Have A Pi Yet?". */}
        <AlertTitle className="text-current first-letter:uppercase">{title ?? defaultTitle}</AlertTitle>
        {children ? (
          <AlertDescription className="text-base text-foreground [&>*:last-child]:mb-0">{children}</AlertDescription>
        ) : null}
      </Alert>
    );
  };
}

const AdmonitionTypeNote = createAdmonitionType({
  variant: "default",
  icon: NotepadText,
  defaultTitle: (
    <Translate id="theme.admonition.note" description="The default label used for the Note admonition (:::note)">
      note
    </Translate>
  ),
});

const AdmonitionTypeTip = createAdmonitionType({
  variant: "success",
  icon: Lightbulb,
  defaultTitle: (
    <Translate id="theme.admonition.tip" description="The default label used for the Tip admonition (:::tip)">
      tip
    </Translate>
  ),
});

const AdmonitionTypeInfo = createAdmonitionType({
  variant: "info",
  icon: Info,
  defaultTitle: (
    <Translate id="theme.admonition.info" description="The default label used for the Info admonition (:::info)">
      info
    </Translate>
  ),
});

const AdmonitionTypeWarning = createAdmonitionType({
  variant: "warning",
  icon: TriangleAlert,
  defaultTitle: (
    <Translate
      id="theme.admonition.warning"
      description="The default label used for the Warning admonition (:::warning)"
    >
      warning
    </Translate>
  ),
});

const AdmonitionTypeDanger = createAdmonitionType({
  variant: "destructive",
  icon: OctagonAlert,
  defaultTitle: (
    <Translate id="theme.admonition.danger" description="The default label used for the Danger admonition (:::danger)">
      danger
    </Translate>
  ),
});

/** Deprecated upstream in favour of `:::warning`, but still used in our docs. */
const AdmonitionTypeCaution = createAdmonitionType({
  variant: "warning",
  icon: TriangleAlert,
  defaultTitle: (
    <Translate
      id="theme.admonition.caution"
      description="The default label used for the Caution admonition (:::caution)"
    >
      caution
    </Translate>
  ),
});

const admonitionTypes: { [admonitionType: string]: ComponentType<Props> } = {
  note: AdmonitionTypeNote,
  tip: AdmonitionTypeTip,
  info: AdmonitionTypeInfo,
  warning: AdmonitionTypeWarning,
  danger: AdmonitionTypeDanger,
};

// Undocumented legacy aliases, kept 1:1 with upstream's hardcoded titles.
const admonitionAliases: { [admonitionType: string]: ComponentType<Props> } = {
  secondary: (props) => <AdmonitionTypeNote title="secondary" {...props} />,
  important: (props) => <AdmonitionTypeInfo title="important" {...props} />,
  success: (props) => <AdmonitionTypeTip title="success" {...props} />,
  caution: AdmonitionTypeCaution,
};

export default {
  ...admonitionTypes,
  ...admonitionAliases,
};
