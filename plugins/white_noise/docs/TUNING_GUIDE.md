# White Noise Plugin - Tuning Guide

This guide helps you find the ideal "sane defaults" for your white noise plugin by experimenting with different settings.

## Available Tuning Parameters

### 1. Intensity (Preset Mode)

Pre-configured intensity levels for quick setup:

| Preset | Drops/Frame | Description | Use Case |
|--------|-------------|-------------|----------|
| `light` | 3 | Minimal sound, very gentle | Sleep, meditation, background ambiance |
| `medium` | 6 | Moderate activity | General relaxation, office environments |
| `heavy` | 10 | Active rain sound | Masking other sounds, active ambiance |
| `custom` | Variable | Manual control | Experimentation, fine-tuning |

### 2. Drops Per Frame (Custom Mode Only)

**Range**: 1-22 drops  
**Default**: 3  
**Description**: Number of new raindrops spawned each frame

#### Recommended Values:

- **1-2 drops**: Ultra-minimal, very sparse sound (good for sleep)
- **3-5 drops**: Gentle pitter-patter (default range)
- **6-8 drops**: Moderate rain activity
- **9-12 drops**: Active rain sound
- **13-22 drops**: Heavy rain (may be overwhelming on fast refresh)

### 3. Max Simultaneous Drops

**Range**: 1-132 drops (6 rows × 22 columns = 132 total tiles)  
**Default**: 30  
**Description**: Maximum number of raindrops allowed on the board at once

#### Recommended Values:

- **10-20 drops**: Very sparse, minimalist aesthetic
- **25-40 drops**: Balanced coverage (default range)
- **45-70 drops**: Dense rain, busy visual
- **80-132 drops**: Very dense, may obscure board readability

### 4. Drop Color

**Options**: `white`, `blue`, `violet`  
**Default**: `white`  
**Description**: Tile color for raindrops

- **White**: Classic rain, highest contrast
- **Blue**: Water-like, cooler aesthetic
- **Violet**: Unique "purple rain" effect

## Experimentation Workflow

### Step 1: Start with Presets

Begin with the preset intensity levels to get a baseline:

1. Set intensity to `light` and refresh interval to 5 seconds
2. Observe the visual effect and sound level
3. Try `medium` and `heavy` to compare

### Step 2: Switch to Custom Mode

Once you understand the presets, switch to custom for fine control:

```json
{
  "intensity": "custom",
  "drops_per_frame": 3,
  "max_drops": 30,
  "drop_color": "white"
}
```

### Step 3: Tune Drops Per Frame

Adjust `drops_per_frame` to control sound intensity:

- **Too quiet?** Increase by 2-3 drops at a time
- **Too loud?** Decrease by 1-2 drops at a time
- **Just right?** Note the value as your "sane default"

### Step 4: Tune Max Drops

Adjust `max_drops` to control visual density:

- **Too sparse?** Increase by 10-15 drops
- **Too cluttered?** Decrease by 10-15 drops
- **Balanced?** Note the value

### Step 5: Optimize Refresh Interval

The refresh interval (how often the board updates) significantly affects the experience:

- **Slower (10-15 seconds)**: Each frame lingers, very gentle pace
- **Medium (5-7 seconds)**: Balanced animation speed (recommended)
- **Faster (2-3 seconds)**: Active animation, more frequent sound
- **Very fast (1 second)**: Rapid animation, may be overwhelming

## Example Configurations

### Configuration 1: Ultra-Minimal Sleep Mode

```json
{
  "intensity": "custom",
  "drops_per_frame": 1,
  "max_drops": 15,
  "drop_color": "blue"
}
```

**Refresh Interval**: 10 seconds  
**Use Case**: Bedroom, sleep aid, very quiet ambiance

### Configuration 2: Balanced Office Mode

```json
{
  "intensity": "custom",
  "drops_per_frame": 4,
  "max_drops": 35,
  "drop_color": "white"
}
```

**Refresh Interval**: 5 seconds  
**Use Case**: Office, background noise, focus aid

### Configuration 3: Active Relaxation

```json
{
  "intensity": "custom",
  "drops_per_frame": 7,
  "max_drops": 50,
  "drop_color": "white"
}
```

**Refresh Interval**: 3 seconds  
**Use Case**: Living room, masking other sounds, active ambiance

### Configuration 4: Heavy Rain Aesthetic

```json
{
  "intensity": "custom",
  "drops_per_frame": 12,
  "max_drops": 70,
  "drop_color": "blue"
}
```

**Refresh Interval**: 4 seconds  
**Use Case**: Visual interest, strong white noise, weather simulation

## Finding Your "Sane Defaults"

### For Most Users

Start with these as your baseline "sane defaults":

- **Intensity**: `light` or `custom` with `drops_per_frame: 3`
- **Max Drops**: `30`
- **Drop Color**: `white`
- **Refresh Interval**: 5 seconds

This provides a gentle, unobtrusive rain effect suitable for most environments.

### Adjusting for Physical Vestaboard

If using a physical Vestaboard (vs. digital display):

- **Sound Sensitivity**: Physical boards make actual mechanical sounds
  - If too loud: Reduce `drops_per_frame` to 1-2
  - If too quiet: Increase to 4-6
- **Room Size**: Larger rooms may benefit from more active settings
- **Time of Day**: Use lower settings for evening/night

### Adjusting for Digital Display Only

If using only the digital display (no physical board):

- Visual density matters more than "sound"
- Can use higher `max_drops` values (50-80) for visual interest
- Faster refresh intervals (2-3 seconds) work well digitally

## Testing Checklist

Use this checklist to systematically find your ideal settings:

- [ ] Test `light`, `medium`, `heavy` presets
- [ ] Switch to `custom` mode
- [ ] Test `drops_per_frame` from 1 to 10 in increments of 2
- [ ] Test `max_drops` at 15, 30, 50, 70
- [ ] Try different `drop_color` options
- [ ] Test refresh intervals from 2 to 10 seconds
- [ ] Document your favorite combination
- [ ] Test at different times of day
- [ ] Get feedback from others in the space

## Recommendations Summary

Based on the plugin design goals (gentle, soothing white noise):

### Conservative Defaults (Recommended for Most)

```json
{
  "intensity": "light",
  "drop_color": "white"
}
```

With default values:
- `drops_per_frame`: 3
- `max_drops`: 30
- Refresh interval: 5-7 seconds

### Custom Experimental Range

For finding your perfect settings:

- **drops_per_frame**: Test 1-8 (beyond 8 may be too active)
- **max_drops**: Test 20-50 (beyond 50 may be too cluttered)
- **refresh_interval**: Test 3-10 seconds

## Feedback

As you experiment, please provide feedback on:

1. What settings worked best for your environment?
2. What should the default `drops_per_frame` be?
3. What should the default `max_drops` be?
4. Should we add more preset intensity levels?

This will help establish the best "sane defaults" for future users.
