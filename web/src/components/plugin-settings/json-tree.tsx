"use client";

import { Box, Flex, Stack, Text } from "@fiestaboard/ui";
import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import React, { useState } from "react";

/**
 * A collapsible JSON tree whose every leaf offers its own dot/bracket path.
 *
 * It knows nothing about plugins, settings, or where the data came from — it
 * renders a value and reports the path the user picked — so any surface that
 * needs "show me this response and let me point at part of it" can use it.
 */
export interface JsonTreeProps {
  data: unknown;
  path: string;
  onSelect: (path: string, value: unknown) => void;
  defaultExpanded?: boolean;
}

export function JsonTree({ data, path, onSelect, defaultExpanded = false }: JsonTreeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(path, data);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (data === null || data === undefined) {
    return (
      <Text as="span" size="xs" tone="muted" className="italic">
        null
      </Text>
    );
  }

  if (typeof data === "object" && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>);
    return (
      <Box className="ml-1">
        <button
          type="button"
          className="flex items-center gap-1 text-xs hover:bg-muted/60 rounded px-1 py-0.5 -ml-1 w-full text-left"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
          <Text as="span" size="xs" tone="muted">{`{${entries.length}}`}</Text>
        </button>
        {expanded && (
          <Stack gap="0.5" className="ml-3 border-l border-border pl-2">
            {entries.map(([key, val]) => {
              const childPath = path ? `${path}.${key}` : key;
              const isLeaf = val === null || val === undefined || typeof val !== "object";
              return (
                <Flex key={key} align="start" gap="1">
                  <Text
                    as="span"
                    size="xs"
                    weight="medium"
                    className="text-blue-600 dark:text-blue-400 shrink-0 pt-0.5"
                  >
                    {key}:
                  </Text>
                  {isLeaf ? (
                    <Flex align="center" gap="1" className="group min-w-0">
                      <Text as="span" size="xs" className="truncate">
                        {String(val ?? "null")}
                      </Text>
                      <button
                        type="button"
                        onClick={handleCopy.bind(null, { stopPropagation: () => {} } as React.MouseEvent)}
                        onClickCapture={(e) => {
                          e.stopPropagation();
                          onSelect(childPath, val);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1500);
                        }}
                        className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 rounded hover:bg-muted"
                        title={`Use path: ${childPath}`}
                      >
                        {copied ? (
                          <Check className="h-3 w-3 text-green-600" />
                        ) : (
                          <Copy className="h-3 w-3 text-muted-foreground" />
                        )}
                      </button>
                    </Flex>
                  ) : (
                    <JsonTree data={val} path={childPath} onSelect={onSelect} />
                  )}
                </Flex>
              );
            })}
          </Stack>
        )}
      </Box>
    );
  }

  if (Array.isArray(data)) {
    return (
      <Box className="ml-1">
        <button
          type="button"
          className="flex items-center gap-1 text-xs hover:bg-muted/60 rounded px-1 py-0.5 -ml-1 w-full text-left"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
          <Text as="span" size="xs" tone="muted">{`[${data.length}]`}</Text>
        </button>
        {expanded && (
          <Stack gap="0.5" className="ml-3 border-l border-border pl-2">
            {data.map((item, idx) => {
              const childPath = path ? `${path}[${idx}]` : `[${idx}]`;
              const isLeaf = item === null || item === undefined || typeof item !== "object";
              return (
                <Flex key={idx} align="start" gap="1">
                  <Text
                    as="span"
                    size="xs"
                    weight="medium"
                    className="text-purple-600 dark:text-purple-400 shrink-0 pt-0.5"
                  >
                    [{idx}]:
                  </Text>
                  {isLeaf ? (
                    <Flex align="center" gap="1" className="group min-w-0">
                      <Text as="span" size="xs" className="truncate">
                        {String(item ?? "null")}
                      </Text>
                      <button
                        type="button"
                        onClickCapture={(e) => {
                          e.stopPropagation();
                          onSelect(childPath, item);
                        }}
                        className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 rounded hover:bg-muted"
                        title={`Use path: ${childPath}`}
                      >
                        <Copy className="h-3 w-3 text-muted-foreground" />
                      </button>
                    </Flex>
                  ) : (
                    <JsonTree data={item} path={childPath} onSelect={onSelect} />
                  )}
                </Flex>
              );
            })}
          </Stack>
        )}
      </Box>
    );
  }

  return (
    <Text as="span" size="xs">
      {String(data)}
    </Text>
  );
}
