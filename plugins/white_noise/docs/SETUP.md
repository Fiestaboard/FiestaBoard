# White Noise Plugin Setup Guide

The White Noise plugin creates a gentle rain effect on your FiestaBoard, producing a soothing ambient pitter-patter sound as white tiles cascade down the display.

## Installation

The White Noise plugin comes bundled with FiestaBoard and requires no additional API keys or external services.

## Configuration

### Using the Web UI

1. Navigate to **Settings** in the FiestaBoard web interface
2. Find the **White Noise** plugin in the plugins list
3. Toggle **Enable White Noise** to activate the plugin
4. Configure the rain effect:
   - **Rain Intensity**: Choose how many drops appear per frame
     - `light` (3 drops) - Gentle drizzle, minimal sound
     - `medium` (6 drops) - Moderate rain
     - `heavy` (10 drops) - Steady rain
   - **Drop Color**: Select the tile color for raindrops
     - `white` - Classic rain effect
     - `blue` - Cool, water-like appearance
     - `violet` - Purple rain aesthetic

### Using Environment Variables

Alternatively, configure via environment variables:

```bash
WHITE_NOISE_ENABLED=true
WHITE_NOISE_INTENSITY=light
WHITE_NOISE_DROP_COLOR=white
```

## Using on a Board

### Adding to a Template

To display the white noise effect on a board, use the `{white_noise}` variable in your board template:

```
{white_noise}
```

This will render the full 6-row × 22-column rain animation.

### Recommended Settings

For the best ambient white noise experience:

- **Intensity**: Start with `light` (default) - it only changes 3 tiles per frame, creating a gentle sound
- **Refresh Interval**: Use a slow refresh rate (e.g., 5-10 seconds) so each frame lingers before the next gentle shift
- **Standalone Display**: The white noise effect works best as a dedicated board rather than mixed with other content

## Visual Examples

### Light Intensity (Default)

![White Noise - Light Intensity](./white-noise-light.png)

*Light rain mode with 3 drops per frame - gentle and minimal*

### Medium Intensity

![White Noise - Medium Intensity](./white-noise-medium.png)

*Medium rain mode with 6 drops per frame - moderate activity*

### Heavy Intensity

![White Noise - Heavy Intensity](./white-noise-heavy.png)

*Heavy rain mode with 10 drops per frame - steady rain effect*

### Color Variations

![White Noise - Blue Drops](./white-noise-blue.png)

*Blue drops create a water-like appearance*

![White Noise - Violet Drops](./white-noise-violet.png)

*Violet drops for a "purple rain" aesthetic*

## Tips

- **For Sleep/Relaxation**: Use `light` intensity with white drops and a 5-10 second refresh interval
- **For Visual Interest**: Try `medium` or `heavy` intensity with colored drops
- **Sound Sensitivity**: Remember that more drops = more tile flips = more sound. Start with `light` and adjust up if desired
- **Template Usage**: The white noise effect is designed to fill the entire board, so it works best as the only content on a template

## Troubleshooting

### No rain appears on the board

- Verify that `WHITE_NOISE_ENABLED=true` or the plugin is enabled in the web UI
- Check that your board template includes the `{white_noise}` variable
- Ensure the board is refreshing (check your refresh interval settings)

### Too much noise/sound

- Switch to `light` intensity (only 3 drops per frame)
- Increase the refresh interval to slow down the animation
- Consider whether the white noise plugin is right for your use case

### Want faster animation

- Decrease the board refresh interval
- Note: Faster refresh = more frequent tile changes = more sound

## Support

For issues or questions about the White Noise plugin, please open an issue on the [FiestaBoard GitHub repository](https://github.com/FiestaBoard/FiestaBoard/issues).
