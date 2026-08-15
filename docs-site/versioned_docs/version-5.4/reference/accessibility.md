---
sidebar_position: 5
description: "FiestaBoard's commitment to WCAG 2.2 Level AAA accessibility compliance."
keywords: [FiestaBoard, accessibility, WCAG, WCAG 2.2, AAA, a11y, assistive technology]
---

# Accessibility

FiestaBoard aims to conform to the [Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/) at the **AAA** level. This is the highest tier of the WCAG standard, and it guides every decision we make about the web UI.

## What This Means

WCAG 2.2 AAA covers a wide range of requirements across four principles:

- **Perceivable** — Content is presented in ways that all users can perceive, including text alternatives for images, captions, and enhanced contrast (minimum 7:1 ratio for normal text).
- **Operable** — The interface is fully navigable by keyboard, provides visible focus indicators, and avoids content that could cause seizures or motion sickness.
- **Understandable** — Text is readable and predictable. Forms include labels, instructions, and helpful error messages.
- **Robust** — Markup is valid and compatible with current and future assistive technologies.

## Contributing Accessible Code

If you are contributing to FiestaBoard, please keep these guidelines in mind:

- Use **semantic HTML** elements (`<button>`, `<nav>`, `<main>`, headings in order, etc.) instead of generic `<div>` or `<span>` elements with click handlers.
- Provide **text alternatives** — every meaningful image should have descriptive `alt` text.
- Ensure **color is not the only indicator** — do not rely solely on color to convey information. Use text labels, icons, or patterns alongside color.
- Maintain **sufficient color contrast** — aim for at least a 7:1 contrast ratio for normal text and 4.5:1 for large text (WCAG AAA).
- Support **keyboard navigation** — all interactive elements must be reachable and operable with the keyboard alone.
- Use **ARIA attributes** only when native HTML semantics are insufficient. Prefer native elements over ARIA roles.
- Test changes with a **screen reader** (e.g., VoiceOver, NVDA) when possible.

## Reporting Accessibility Issues

If you encounter an accessibility barrier in FiestaBoard, please let us know:

- [Open an issue on GitHub](https://github.com/Fiestaboard/FiestaBoard/issues) with the **accessibility** label.
- Describe the barrier, the page or component affected, and the assistive technology you were using (if applicable).
- You can also reach out on [Discord](https://discord.gg/2GAqKnRF6h).

We treat accessibility issues with the same priority as bugs.
