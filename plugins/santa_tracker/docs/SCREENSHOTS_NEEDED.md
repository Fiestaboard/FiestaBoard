# Screenshots Needed for Santa Tracker Plugin

This document outlines the screenshots required to complete the plugin documentation.

## Required Screenshots

### 1. `santa-tracker-display.png`
**Location:** `plugins/santa_tracker/docs/`

**What to capture:** The Santa Tracker plugin displaying on a FiestaBoard during Christmas delivery (when Santa is actively traveling).

**Setup:**
1. Enable the Santa Tracker plugin in the FiestaBoard web UI
2. Configure a board template to display Santa Tracker variables
3. If testing outside of December 25th, you may need to modify system date/time or use the `year` config setting
4. Capture the full board display showing the plugin output

**Expected content:**
- Status: "Santa is delivering presents!"
- Current location (e.g., "Paris, France")
- Progress indicator showing percentage

---

### 2. `santa-tracker-in-action.png`
**Location:** `plugins/santa_tracker/docs/`

**What to capture:** A wider view showing the Santa Tracker in context of the full FiestaBoard interface.

**Setup:**
1. Have the plugin enabled and displaying on a board
2. Show enough context to see how it integrates with the overall board

**Expected content:**
- Full board view with Santa Tracker visible
- Shows how the plugin integrates with other board elements

---

### 3. `santa-before-christmas.png`
**Location:** `plugins/santa_tracker/docs/`

**What to capture:** The plugin state before December 25th arrives in any timezone.

**Setup:**
1. Test on a date before December 24th, or adjust system time
2. Display on a board

**Expected content:**
- Status: "Santa is getting ready for 2026"
- Location: "North Pole"

---

### 4. `santa-during-delivery.png`
**Location:** `plugins/santa_tracker/docs/`

**What to capture:** The plugin state during active Christmas delivery.

**Setup:**
1. Test on December 25th during the delivery window, or adjust system time to December 25th when some but not all timezones have crossed midnight
2. Display on a board

**Expected content:**
- Status: "Santa is delivering presents!"
- Current location (e.g., "Tokyo, Japan" or "London, England")
- Next stop location
- Progress percentage (between 1-99%)

---

### 5. `santa-after-christmas.png`
**Location:** `plugins/santa_tracker/docs/`

**What to capture:** The plugin state after December 25th has ended in all timezones.

**Setup:**
1. Test on December 26th or later, or adjust system time
2. Display on a board

**Expected content:**
- Status: "Santa is done for 2026"

---

## How to Test Different States

### Method 1: Change System Date (Development)
```bash
# Before Christmas
sudo date -s "2026-12-24 12:00:00"

# During delivery (early stops)
sudo date -s "2026-12-25 01:00:00"

# During delivery (middle stops)
sudo date -s "2026-12-25 12:00:00"

# After Christmas
sudo date -s "2026-12-26 12:00:00"

# Don't forget to restore:
sudo ntpdate -s time.nist.gov
```

### Method 2: Use Plugin Configuration
- Set the `year` config to a year in the past (e.g., 2025) to see "done" state
- Set to future year and adjust expectations accordingly

### Method 3: Modify Test Code (Temporary)
You could temporarily modify the plugin code to return specific states for testing purposes, but remember to revert changes before committing.

## Screenshot Guidelines

- **Resolution:** Capture at a reasonable resolution (1920x1080 or similar)
- **Format:** PNG format for clarity
- **Crop:** Crop screenshots to show relevant content without excessive whitespace
- **Lighting:** If photographing a physical e-ink display, ensure good lighting and minimal glare
- **Context:** Include enough context to understand what's being shown
- **Quality:** Images should be clear and readable

## After Capturing Screenshots

1. Save all screenshots to `plugins/santa_tracker/docs/` directory
2. Verify filenames match exactly:
   - `santa-tracker-display.png`
   - `santa-tracker-in-action.png`
   - `santa-before-christmas.png`
   - `santa-during-delivery.png`
   - `santa-after-christmas.png`
3. Verify images display correctly in the markdown files
4. Delete this `SCREENSHOTS_NEEDED.md` file
5. Commit and push the screenshot images
