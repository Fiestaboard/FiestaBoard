#!/usr/bin/env node

/**
 * Test runner wrapper that suppresses jsdom localStorage warnings
 * These warnings are internal to jsdom and don't affect our application or tests
 *
 * This script filters stderr to remove the specific warning while preserving all other output
 */

import { spawn } from "child_process";
import { Transform } from "stream";

// Get the command and arguments
const [, , command, ...args] = process.argv;

if (!command) {
  console.error("Usage: node suppress-warnings.mjs <command> [args...]");
  process.exit(1);
}

// Create a transform stream to filter warnings
const filterWarnings = new Transform({
  transform(chunk, encoding, callback) {
    const text = chunk.toString();
    const lines = text.split("\n");
    const filtered = lines
      .filter((line) => !line.includes("--localstorage-file"))
      .filter((line) => !line.includes("(Use `node --trace-warnings ...` to show where the warning was created)"))
      .join("\n");

    // Only push if there's content after filtering empty lines
    if (filtered.trim()) {
      this.push(filtered);
    }
    callback();
  },
});

// Spawn the command (use npx for vitest since it might not be in PATH)
const child = spawn(command, args, {
  stdio: ["inherit", "inherit", "pipe"], // Pipe stderr so we can filter it
  env: process.env,
});

// Filter stderr
child.stderr.pipe(filterWarnings).pipe(process.stderr);

child.on("exit", (code) => {
  process.exit(code || 0);
});

child.on("error", (error) => {
  console.error("Failed to start process:", error);
  process.exit(1);
});
