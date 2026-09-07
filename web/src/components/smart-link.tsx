import { TextLink } from "@fiestaboard/ui";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { Link as RRLink } from "react-router";

type SmartLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  replace?: boolean;
  // Accepted-and-ignored for source compatibility with prior `next/link`
  // call sites. RR7 has no equivalent prefetch toggle at the Link level.
  prefetch?: boolean | null;
  scroll?: boolean;
  shallow?: boolean;
  passHref?: boolean;
  legacyBehavior?: boolean;
  locale?: string | false;
  as?: string;
  children?: ReactNode;
};

const EXTERNAL = /^([a-z][a-z0-9+.-]*:|\/\/)/i;

export default function SmartLink({
  href,
  replace,
  prefetch: _prefetch,
  scroll: _scroll,
  shallow: _shallow,
  passHref: _passHref,
  legacyBehavior: _legacyBehavior,
  locale: _locale,
  as: _as,
  children,
  ...rest
}: SmartLinkProps) {
  if (EXTERNAL.test(href)) {
    return (
      <TextLink href={href} {...rest}>
        {children}
      </TextLink>
    );
  }
  return (
    <RRLink to={href} replace={replace} {...rest}>
      {children}
    </RRLink>
  );
}
