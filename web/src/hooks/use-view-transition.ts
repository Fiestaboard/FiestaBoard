"use client";

import { useCallback } from "react";

import { useRouter } from "@/hooks/use-router";

type TransitionType = "default" | "slide-up" | "slide-down" | "scale-fade";

interface ViewTransitionOptions {
  transitionType?: TransitionType;
}

export function useViewTransition() {
  const router = useRouter();

  const push = useCallback(
    (href: string, options: ViewTransitionOptions = {}) => {
      const { transitionType = "default" } = options;

      // Apply transition class for CSS animations
      if (transitionType !== "default" && document.documentElement) {
        document.documentElement.dataset.transition = transitionType;
      }

      // Navigate
      router.push(href);

      // Clean up transition class after animation
      setTimeout(() => {
        if (document.documentElement) {
          delete document.documentElement.dataset.transition;
        }
      }, 500);
    },
    [router],
  );

  const replace = useCallback(
    (href: string, options: ViewTransitionOptions = {}) => {
      const { transitionType = "default" } = options;

      // Apply transition class for CSS animations
      if (transitionType !== "default" && document.documentElement) {
        document.documentElement.dataset.transition = transitionType;
      }

      // Navigate
      router.replace(href);

      // Clean up transition class after animation
      setTimeout(() => {
        if (document.documentElement) {
          delete document.documentElement.dataset.transition;
        }
      }, 500);
    },
    [router],
  );

  const back = useCallback(
    (options: ViewTransitionOptions = {}) => {
      const { transitionType = "slide-down" } = options;

      // Apply transition class for CSS animations
      if (transitionType !== "default" && document.documentElement) {
        document.documentElement.dataset.transition = transitionType;
      }

      // Navigate
      router.back();

      // Clean up transition class after animation
      setTimeout(() => {
        if (document.documentElement) {
          delete document.documentElement.dataset.transition;
        }
      }, 500);
    },
    [router],
  );

  return {
    push,
    replace,
    back,
  };
}
