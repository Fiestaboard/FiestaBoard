# Screenshots Needed for White Noise Plugin

This document outlines the screenshots needed to complete the documentation for the White Noise plugin.

## Required Screenshots

All screenshots should be placed in the `/workspace/plugins/white_noise/docs/` directory with the filenames listed below.

### 1. Main Display Screenshot
**Filename**: `white-noise-display.png`  
**Description**: Hero image showing the white noise plugin in action on a FiestaBoard  
**Configuration**:
- Intensity: light
- Drop Color: white
- Show the board with white tiles cascading down

### 2. Light Intensity Example
**Filename**: `white-noise-light.png`  
**Description**: Light rain mode with minimal drops  
**Configuration**:
- Intensity: light (3 drops per frame)
- Drop Color: white
- Capture a frame showing sparse rain effect

### 3. Medium Intensity Example
**Filename**: `white-noise-medium.png`  
**Description**: Medium rain mode with moderate drops  
**Configuration**:
- Intensity: medium (6 drops per frame)
- Drop Color: white
- Capture a frame showing moderate rain effect

### 4. Heavy Intensity Example
**Filename**: `white-noise-heavy.png`  
**Description**: Heavy rain mode with many drops  
**Configuration**:
- Intensity: heavy (10 drops per frame)
- Drop Color: white
- Capture a frame showing dense rain effect

### 5. White Color Example
**Filename**: `white-noise-white.png`  
**Description**: Rain effect with white colored drops  
**Configuration**:
- Intensity: medium
- Drop Color: white

### 6. Blue Color Example
**Filename**: `white-noise-blue.png`  
**Description**: Rain effect with blue colored drops  
**Configuration**:
- Intensity: medium
- Drop Color: blue

### 7. Violet Color Example
**Filename**: `white-noise-violet.png`  
**Description**: Rain effect with violet colored drops  
**Configuration**:
- Intensity: medium
- Drop Color: violet

## How to Capture Screenshots

### Option 1: From the FiestaBoard Web App

1. Start the FiestaBoard development environment:
   ```bash
   docker-compose -f docker-compose.dev.yml up
   ```

2. Navigate to `http://localhost:4420` in your browser

3. Configure the white noise plugin:
   - Go to the **Integrations** page
   - Toggle the **White Noise** plugin on
   - Configure the desired intensity and color settings
   - Click **Save Changes**

4. Create a page template with `{white_noise.white_noise}` as the content

5. View the board and capture screenshots:
   - Use your browser's screenshot tool or operating system's screenshot utility
   - Crop to show just the board display
   - Save with the appropriate filename in `/workspace/plugins/white_noise/docs/`

### Option 2: From a Physical Vestaboard

If you have access to a physical Vestaboard:

1. Configure the white noise plugin with the desired settings
2. Take a photograph of the Vestaboard display showing the rain effect
3. Crop and optimize the image
4. Save with the appropriate filename

### Option 3: Programmatic Screenshot (if web app supports it)

If the FiestaBoard web app has a screenshot API or export function, use that to capture consistent screenshots for each configuration.

## Screenshot Specifications

- **Format**: PNG (preferred) or JPEG
- **Size**: Maintain aspect ratio of a 6×22 Vestaboard display
- **Quality**: High resolution, clear and readable
- **Background**: Show the full board, avoid cropping tile edges
- **Consistency**: Use the same board/display for all screenshots if possible

## After Capturing Screenshots

1. Place all screenshots in `/workspace/plugins/white_noise/docs/`
2. Verify filenames match exactly (case-sensitive)
3. Check that images are referenced correctly in:
   - `/workspace/plugins/white_noise/README.md`
   - `/workspace/plugins/white_noise/docs/SETUP.md`
4. Delete this `SCREENSHOTS_NEEDED.md` file once all screenshots are captured

## Notes

- Screenshots should show actual plugin output, not mockups
- Capture frames that clearly show the rain cascade effect
- For intensity comparisons, capture frames at similar points in the animation
- Ensure color screenshots clearly show the difference between white, blue, and violet drops
