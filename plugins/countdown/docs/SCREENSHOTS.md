# Screenshot Guide for Countdown Plugin

This document describes the screenshots needed for the Countdown plugin documentation.

## Required Screenshots

### 1. Integrations List (`integrations-list.png`)

**Location:** `plugins/countdown/docs/integrations-list.png`

**What to capture:**
- Navigate to the **Integrations** page in the FiestaBoard web UI
- Scroll to find the **Countdown** plugin in the list
- Ensure the plugin is visible with its timer icon
- Capture the integrations page showing the Countdown plugin entry

**Expected content:**
- Countdown plugin card with timer icon
- Plugin name "Countdown"
- Toggle switch (on or off)
- Description: "Display the remaining time to an event in real time"

---

### 2. Configuration Dialog (`configuration-dialog.png`)

**Location:** `plugins/countdown/docs/configuration-dialog.png`

**What to capture:**
- Enable the Countdown plugin if not already enabled
- Click the **Configure** button on the Countdown plugin
- Fill in example values:
  - **Event Name:** `Last Day of School`
  - **Target Date & Time:** `2025-06-15T00:00:00`
  - **Timezone:** `America/Los_Angeles`
- Capture the configuration dialog with these values filled in

**Expected content:**
- Modal/dialog showing configuration form
- Event Name field with example value
- Target Date & Time field (datetime picker or text input)
- Timezone field with dropdown/autocomplete
- Save and Cancel buttons

---

### 3. Page Editor (`page-editor.png`)

**Location:** `plugins/countdown/docs/page-editor.png`

**What to capture:**
- Navigate to **Pages** in the web UI
- Create a new page or edit an existing one
- Add a countdown template in the editor:
  ```
  {center}COUNTDOWN UNTIL
  {{countdown.event_name}}
  
  {{countdown.days}} DAYS
  {{countdown.hours}} HOURS
  {{countdown.minutes}} MINUTES
  ```
- Capture the page editor showing:
  - The template on the left side
  - Live preview of the rendered countdown on the right side

**Expected content:**
- Split view: template editor on left, board preview on right
- Template variables visible in the editor
- Preview showing the countdown with real values rendered
- Save button visible

---

### 4. Board Display (`board-display.png`)

**Location:** `plugins/countdown/docs/board-display.png`

**What to capture:**
- A photo or screenshot of the actual Vestaboard (or compatible display) showing the countdown
- Use the classic countdown template format
- Ensure the display is clear and readable

**Expected content:**
- Physical board showing:
  ```
     COUNTDOWN UNTIL
   LAST DAY OF SCHOOL
  
         22 DAYS
         3 HOURS
        10 MINUTES
  ```
- Clear, well-lit photo showing the split-flap characters
- Centered text as formatted in the template

**Alternative:**
If a physical board photo is not available, use the web UI preview showing the rendered countdown display.

---

## How to Capture Screenshots

### Prerequisites
1. Start FiestaBoard with Docker:
   ```bash
   docker-compose -f docker-compose.dev.yml up
   ```
2. Open http://localhost:8080 in your browser
3. Start the service if not already running

### Capture Process
1. Use your OS screenshot tool (or browser dev tools)
2. Crop screenshots to show only relevant UI elements
3. Save as PNG files with the names specified above
4. Place files in `plugins/countdown/docs/`
5. Optimize images to keep file sizes < 500KB

### Image Guidelines
- **Format:** PNG (better for text/UI screenshots)
- **Size:** Keep under 500KB each
- **Quality:** High enough to read text clearly
- **Crop:** Remove unnecessary browser chrome/toolbars
- **Privacy:** Do not include personal information (use example data as shown)

---

## Verification

After adding screenshots, verify:
- [ ] All 4 screenshot files exist in `plugins/countdown/docs/`
- [ ] Images are referenced correctly in `SETUP.md`
- [ ] Images are referenced correctly in `README.md`
- [ ] File sizes are reasonable (< 500KB each)
- [ ] Screenshots show example data (not personal information)
- [ ] Text in screenshots is readable
- [ ] Screenshots match the documentation descriptions

---

## Example Values to Use

When capturing screenshots, use these non-personal example values:

- **Event Name:** `Last Day of School`, `Product Launch`, or `Holiday Party`
- **Target Date:** Use a future date like `2025-06-15T00:00:00`
- **Timezone:** `America/Los_Angeles`, `America/New_York`, or `UTC`
- **Page Name:** `Countdown Display` or `Event Countdown`

Do NOT use:
- Real personal event dates
- Real addresses or coordinates
- Personal names or information
