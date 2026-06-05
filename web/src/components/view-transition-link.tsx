"use client";

import Link from "next/link";
import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from "react";

type TransitionType = "default" | "slide-up" | "slide-down" | "scale-fade";

interface ViewTransitionLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  href: string;
  children: ReactNode;
  transitionType?: TransitionType;
  className?: string;
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
}

export function ViewTransitionLink({
  href,
  children,
  transitionType = "default",
  className,
  onClick,
  ...props
}: ViewTransitionLinkProps) {
  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    // Call user's onClick if provided
    if (onClick) {
      onClick(e);
    }

    // Apply transition class for CSS animations
    if (transitionType !== "default" && document.documentElement) {
      document.documentElement.dataset.transition = transitionType;

      // Clean up after navigation
      setTimeout(() => {
        if (document.documentElement) {
          delete document.documentElement.dataset.transition;
        }
      }, 500);
    }
  };

  return (
    <Link href={href} onClick={handleClick} className={className} prefetch={false} {...props}>
      {children}
    </Link>
  );
}
