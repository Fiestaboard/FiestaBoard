/**
 * Mock board server validation tests.
 *
 * Verifies that the mock Vestaboard API server correctly:
 *  - Rejects character codes outside the valid range (0-71)
 *  - Encodes special characters in text mode
 *  - Validates board dimensions
 */
import { expect, MOCK_BOARD_URL, test } from "./helpers";

test.beforeEach(async () => {
  await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });
});

// ---------------------------------------------------------------------------
// Character code validation
// ---------------------------------------------------------------------------

test.describe("Mock board – character code validation", () => {
  test("accepts valid character array (6x22 with codes 0-71)", async () => {
    const chars = Array.from({ length: 6 }, () => Array(22).fill(0));
    // Sprinkle valid codes
    chars[0][0] = 1; // A
    chars[0][1] = 62; // Degree/Heart
    chars[0][2] = 71; // Filled (max valid)

    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars }),
    });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.ok).toBe(true);
  });

  test("accepts valid 3x15 Note array", async () => {
    const chars = Array.from({ length: 3 }, () => Array(15).fill(0));
    chars[0][0] = 8; // H
    chars[0][1] = 9; // I

    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars }),
    });
    expect(res.status).toBe(200);
  });

  test("rejects character code above 71", async () => {
    const chars = Array.from({ length: 6 }, () => Array(22).fill(0));
    chars[2][5] = 999;

    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars }),
    });
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toContain("Invalid character code 999");
  });

  test("rejects negative character code", async () => {
    const chars = Array.from({ length: 3 }, () => Array(15).fill(0));
    chars[0][0] = -1;

    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars }),
    });
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toContain("Invalid character code -1");
  });

  test("rejects invalid dimensions (4x10)", async () => {
    const chars = Array.from({ length: 4 }, () => Array(10).fill(0));

    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars }),
    });
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toContain("valid board array");
  });
});

// ---------------------------------------------------------------------------
// Text mode encoding
// ---------------------------------------------------------------------------

test.describe("Mock board – text mode encoding", () => {
  test("letters encode to correct character codes", async () => {
    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "ABC", rows: 3, cols: 15 }),
    });
    expect(res.status).toBe(200);

    const state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    const row0 = state.history[0].characters[0];
    expect(row0[0]).toBe(1); // A
    expect(row0[1]).toBe(2); // B
    expect(row0[2]).toBe(3); // C
    expect(row0[3]).toBe(0); // blank
  });

  test("digits encode correctly (1-9 → 27-35, 0 → 36)", async () => {
    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "190", rows: 3, cols: 15 }),
    });
    expect(res.status).toBe(200);

    const state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    const row0 = state.history[0].characters[0];
    expect(row0[0]).toBe(27); // 1
    expect(row0[1]).toBe(35); // 9
    expect(row0[2]).toBe(36); // 0
  });

  test("special characters encode correctly", async () => {
    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "!@+&", rows: 3, cols: 15 }),
    });
    expect(res.status).toBe(200);

    const state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    const row0 = state.history[0].characters[0];
    expect(row0[0]).toBe(37); // !
    expect(row0[1]).toBe(38); // @
    expect(row0[2]).toBe(46); // +
    expect(row0[3]).toBe(47); // &
  });

  test("punctuation encodes correctly", async () => {
    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "-.,:;?/", rows: 3, cols: 15 }),
    });
    expect(res.status).toBe(200);

    const state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    const row0 = state.history[0].characters[0];
    expect(row0[0]).toBe(44); // -
    expect(row0[1]).toBe(56); // .
    expect(row0[2]).toBe(55); // ,
    expect(row0[3]).toBe(50); // :
    expect(row0[4]).toBe(49); // ;
    expect(row0[5]).toBe(60); // ?
    expect(row0[6]).toBe(59); // /
  });

  test("unsupported text dimensions are rejected", async () => {
    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "HELLO", rows: 4, cols: 10 }),
    });
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toContain("Unsupported dimensions");
  });

  test("text wraps to next row on newline", async () => {
    const res = await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "AB\nCD", rows: 3, cols: 15 }),
    });
    expect(res.status).toBe(200);

    const state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    const chars = state.history[0].characters;
    expect(chars[0][0]).toBe(1); // A
    expect(chars[0][1]).toBe(2); // B
    expect(chars[1][0]).toBe(3); // C
    expect(chars[1][1]).toBe(4); // D
  });
});

// ---------------------------------------------------------------------------
// State management
// ---------------------------------------------------------------------------

test.describe("Mock board – state", () => {
  test("reset clears message history", async () => {
    // Send a message
    const chars = Array.from({ length: 6 }, () => Array(22).fill(0));
    chars[0][0] = 1;
    await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars }),
    });

    // Verify message was recorded
    let state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    expect(state.message_count).toBe(1);

    // Reset
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    // Verify reset
    state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    expect(state.message_count).toBe(0);
    expect(state.request_count).toBe(0);
  });

  test("history records dimensions for each message", async () => {
    // Send Flagship message
    const flagship = Array.from({ length: 6 }, () => Array(22).fill(0));
    await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: flagship }),
    });

    // Send Note message
    const note = Array.from({ length: 3 }, () => Array(15).fill(0));
    await fetch(`${MOCK_BOARD_URL}/local-api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: note }),
    });

    const state = await (await fetch(`${MOCK_BOARD_URL}/mock/state`)).json();
    expect(state.message_count).toBe(2);
    expect(state.history[0].dimensions).toEqual([6, 22]);
    expect(state.history[1].dimensions).toEqual([3, 15]);
  });
});
