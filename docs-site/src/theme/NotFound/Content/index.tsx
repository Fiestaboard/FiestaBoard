/**
 * Swizzled `@theme/NotFound/Content` — the 404 page, rebuilt on FiestaUI's
 * `EmptyState` (with `Button` CTAs) rather than Infima's bare hero title and
 * two paragraphs of prose.
 *
 * Upstream's second paragraph asks the visitor to contact whoever linked them,
 * which is not actionable on a docs site that reorganises its own URLs across
 * versions; the CTAs send them somewhere useful instead. The title and first
 * paragraph keep the upstream `theme.NotFound.*` ids so existing locale data
 * still applies; the two button labels are new ids under the same namespace.
 */

import Link from "@docusaurus/Link";
import { translate } from "@docusaurus/Translate";
import useBaseUrl from "@docusaurus/useBaseUrl";
import { Button, EmptyState } from "@fiestaboard/ui";
import type { Props } from "@theme/NotFound/Content";
import clsx from "clsx";
import { Compass } from "lucide-react";
import type { ReactNode } from "react";

export default function NotFoundContent({ className }: Props): ReactNode {
  const homeHref = useBaseUrl("/");
  const docsHref = useBaseUrl("/docs/intro");

  return (
    <main className={clsx("container margin-vert--xl", className)}>
      {/* `EmptyState` is sized for an empty list inside app chrome; a standalone
          404 needs display sizing. Scaled through the component's own
          `data-slot` hooks rather than by forking it. */}
      <EmptyState
        className="py-16 [&_[data-slot=empty-state-description]]:text-base [&_[data-slot=empty-state-title]]:text-2xl [&_[data-slot=empty-state-title]]:font-semibold"
        icon={Compass}
        title={translate({
          id: "theme.NotFound.title",
          description: "The title of the 404 page",
          message: "Page Not Found",
        })}
        description={translate({
          id: "theme.NotFound.p1",
          description: "The first paragraph of the 404 page",
          message: "We could not find what you were looking for.",
        })}
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button asChild>
              <Link to={docsHref} className="no-underline">
                {translate({
                  id: "theme.NotFound.cta.docs",
                  description: "Label for the 404 page button linking to the documentation",
                  message: "Browse the docs",
                })}
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link to={homeHref} className="no-underline">
                {translate({
                  id: "theme.NotFound.cta.home",
                  description: "Label for the 404 page button returning to the homepage",
                  message: "Back to home",
                })}
              </Link>
            </Button>
          </div>
        }
      />
    </main>
  );
}
