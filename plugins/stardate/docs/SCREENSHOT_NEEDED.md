# Screenshot Needed

To complete the documentation for this plugin, a screenshot is needed showing the stardate plugin in use on the FiestaBoard display.

## Screenshot Requirements

**Filename**: `stardate-display.png`  
**Location**: `plugins/stardate/docs/stardate-display.png`

### What to Capture

The screenshot should show the stardate plugin displaying on the FiestaBoard, ideally showing:

1. **The word "STARDATE"** as the header
2. **The negative stardate value** (e.g., `-296854.8`)
3. **The full display context** - how it appears on the actual board

### How to Capture

1. Run the FiestaBoard application
2. Create or navigate to a page using the stardate plugin
3. Either use the `get_formatted_display()` output or a template like:
   ```
   STARDATE
   {{stardate}}
   ```
4. Take a screenshot of the display showing the stardate
5. Save as `plugins/stardate/docs/stardate-display.png`
6. Commit the screenshot to the repository

### Current Value

For reference, today's stardate is approximately **-296854.8** (February 22, 2026).

The negative value indicates we are 297 years before stardate 0 (January 1, 2323), which makes this accurate to Star Trek TNG canon where Season 1 (2364) = stardate 41xxx.
