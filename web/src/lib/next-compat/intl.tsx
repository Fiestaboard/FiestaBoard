/**
 * Compat shim for `next-intl` on react-i18next.
 *
 * 77 files in this codebase import from `next-intl`. The shim mirrors the
 * three APIs they actually use: `useTranslations`, `useLocale`, and
 * `NextIntlClientProvider`. The shim's `t` function supports `t.rich` and
 * `t.raw` with semantics that match the existing vitest mock at
 * `src/__tests__/setup.ts:55-97` (which has been our reference behavior
 * for two years of test coverage). This file lifts that logic to be the
 * production implementation.
 *
 * Implementation note: we delegate value lookup to react-i18next's `t`
 * which returns the raw string for plain keys, but build our own
 * `t.rich` and `t.raw` and re-implement ICU `{name, plural, ...}` so the
 * behavior matches what's been shipping. react-i18next's built-in
 * pluralization is configurable but the existing messages use ICU-style
 * inline plural, so we match that surface.
 */
import React, { Fragment } from "react";
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

type TFn = {
  (key: string, params?: Record<string, unknown>): string;
  rich: (key: string, values?: Record<string, unknown>) => React.ReactNode;
  raw: (key: string) => unknown;
};

export function useTranslations(namespace?: string): TFn {
  // Subscribe to react-i18next so re-renders happen on language change.
  const { t: rrtT, i18n: rrtI18n } = useTranslation();
  void rrtT;
  const language = rrtI18n.language || i18n.language || "en";

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

  t.rich = (key: string, values?: Record<string, unknown>) => {
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
          parts.push(
            React.createElement(Fragment, { key: nodeKey++ }, (fn as (chunks: string) => React.ReactNode)(match[2])),
          );
        } else {
          parts.push(match[2]);
        }
      } else if (match[3]) {
        const v = values[match[3]];
        if (typeof v === "function") {
          parts.push(React.createElement(Fragment, { key: nodeKey++ }, (v as () => React.ReactNode)()));
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
}

export function useLocale(): string {
  const { i18n: rrtI18n } = useTranslation();
  return rrtI18n.language || i18n.language || "en";
}

export function NextIntlClientProvider({
  children,
}: {
  children: React.ReactNode;
  messages?: unknown;
  locale?: string;
}) {
  return <>{children}</>;
}
