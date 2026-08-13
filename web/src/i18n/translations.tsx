/**
 * Translation hook layered over react-i18next.
 *
 * Exposes the shape the codebase has been using for ~2 years:
 *   const t = useTranslations("namespace");
 *   t("key", {count: 3});            // ICU plural via inline regex
 *   t.rich("key", { strong: (c) => <Text as="span" weight="semibold">{c}</Text> });
 *   t.raw("key");                    // raw object / array / string
 *
 * react-i18next's `t` returns the resolved string for plain keys; we
 * build `t.rich` and `t.raw` and re-implement ICU
 * `{name, plural, one {...} other {...}}` directly so the existing
 * `messages/*.json` (which uses next-intl's ICU syntax) keeps working
 * without a per-string codemod across 14 locales.
 */
import React, { Fragment, useMemo } from "react";
import { useTranslation } from "react-i18next";

import i18n from "@/i18n/i18next";

function getNestedRaw(obj: unknown, path: string): unknown {
  if (!path) return obj;
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === "object" && part in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function interpolatePlural(input: string, params?: Record<string, unknown>): string {
  if (!params) return input;
  // ICU plural: {name, plural, one {...} other {...} =0 {...}}
  let out = input.replace(
    /\{(\w+),\s*plural,\s*((?:[^{}]|\{[^{}]*\})*)\}/g,
    (_full: string, name: string, branches: string) => {
      const value = Number(params[name]);
      const branchMap: Record<string, string> = {};
      const branchRe = /(\w+|=\d+)\s*\{([^{}]*)\}/g;
      let m: RegExpExecArray | null;
      while ((m = branchRe.exec(branches)) !== null) {
        branchMap[m[1]] = m[2];
      }
      let chosen = branchMap.other ?? "";
      if (`=${value}` in branchMap) chosen = branchMap[`=${value}`];
      else if (value === 1 && branchMap.one) chosen = branchMap.one;
      return chosen.replace(/#/g, String(value));
    },
  );
  out = out.replace(/\{(\w+)\}/g, (_: string, k: string) => (params[k] != null ? String(params[k]) : `{${k}}`));
  return out;
}

/**
 * A single `t.rich` substitution.
 *
 * Functions cover both placeholder forms the renderer understands:
 * `<tag>chunks</tag>` calls the function with the wrapped text, and
 * `{name}` calls it with no argument (a zero-arity arrow is assignable
 * here, so both spellings get `chunks` contextually typed). Non-function
 * values are stringified in place.
 */
export type RichTranslationValue = ((chunks: string) => React.ReactNode) | string | number | boolean | null | undefined;

type TFn = {
  (key: string, params?: Record<string, unknown>): string;
  rich: (key: string, values?: Record<string, RichTranslationValue>) => React.ReactNode;
  raw: (key: string) => unknown;
};

export function useTranslations(namespace?: string): TFn {
  // Subscribe to react-i18next so re-renders happen on language change.
  const { t: rrtT, i18n: rrtI18n } = useTranslation();
  void rrtT;
  const language = rrtI18n.language || i18n.language || "en";

  // Memoize `t` itself so it's a stable reference across renders as long as
  // the language and namespace haven't changed. Without this, `t` is a new
  // function identity on every render, which makes it unsafe to add to a
  // `useEffect`/`useMemo` dependency array — an effect that unconditionally
  // calls `setState` would re-fire (and re-render) on every render, not just
  // on an actual language change, causing an infinite render loop. Consumers
  // still need `t` in their dependency arrays to recompute derived text on a
  // real language switch (see issue #1570); this makes that safe.
  return useMemo(() => {
    const resources = (i18n.getResourceBundle(language, "translation") ?? {}) as Record<string, unknown>;
    const ns = namespace ? getNestedRaw(resources, namespace) : resources;

    const lookup = (key: string): unknown => {
      const v = getNestedRaw(ns, key);
      if (v === undefined && language !== "en") {
        // Fall back to English if the active locale is missing the key,
        // mirroring i18next's fallbackLng behavior at a per-key level.
        const en = i18n.getResourceBundle("en", "translation") as Record<string, unknown> | undefined;
        const enNs = namespace ? getNestedRaw(en, namespace) : en;
        const enV = getNestedRaw(enNs, key);
        if (enV !== undefined) return enV;
      }
      return v === undefined ? (namespace ? `${namespace}.${key}` : key) : v;
    };

    const t = ((key: string, params?: Record<string, unknown>) => {
      const raw = lookup(key);
      const rawStr = typeof raw === "string" ? raw : namespace ? `${namespace}.${key}` : key;
      return interpolatePlural(rawStr, params);
    }) as TFn;

    t.rich = (key: string, values?: Record<string, RichTranslationValue>) => {
      const rawVal = lookup(key);
      const raw = typeof rawVal === "string" ? rawVal : key;
      if (!values) return raw;
      const parts: React.ReactNode[] = [];
      const regex = /<(\w+)>(.*?)<\/\1>|\{(\w+)\}/g;
      let lastIndex = 0;
      let match: RegExpExecArray | null;
      let nodeKey = 0;
      while ((match = regex.exec(raw)) !== null) {
        if (match.index > lastIndex) {
          parts.push(raw.slice(lastIndex, match.index));
        }
        if (match[1]) {
          const fn = values[match[1]];
          if (typeof fn === "function") {
            parts.push(React.createElement(Fragment, { key: nodeKey++ }, fn(match[2])));
          } else {
            parts.push(match[2]);
          }
        } else if (match[3]) {
          const v = values[match[3]];
          if (typeof v === "function") {
            parts.push(React.createElement(Fragment, { key: nodeKey++ }, v("")));
          } else if (v != null) {
            parts.push(String(v));
          }
        }
        lastIndex = regex.lastIndex;
      }
      if (lastIndex < raw.length) parts.push(raw.slice(lastIndex));
      return React.createElement(Fragment, null, ...parts);
    };

    t.raw = (key: string) => {
      const v = getNestedRaw(ns, key);
      return v === undefined ? key : v;
    };

    return t;
  }, [language, namespace]);
}

export function useLocale(): string {
  const { i18n: rrtI18n } = useTranslation();
  return rrtI18n.language || i18n.language || "en";
}
