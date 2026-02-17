# White Noise Plugin

A gentle rain / white noise mode for FiestaBoard. It shows softly cascading
white (or blue/violet) tiles that drift down the board with only a few
changing at a time — creating a quiet, soothing pitter-patter on the
physical Vestaboard.

## How It Works

Each refresh cycle the plugin:

1. **Moves** existing raindrops down by one row.
2. **Removes** drops that have fallen off the bottom of the board.
3. **Spawns** a small number of new drops along the top row at random
   columns.

Because only a handful of tiles flip between frames, the board produces a
gentle "light rain" sound instead of an overwhelming clatter.

## Settings

| Setting     | Default  | Description                                       |
| ----------- | -------- | ------------------------------------------------- |
| `intensity` | `light`  | `light` (3 drops), `medium` (6), or `heavy` (10)  |
| `drop_color`| `white`  | Tile colour for drops: `white`, `blue`, `violet`  |

## Variables

| Variable        | Description                                    |
| --------------- | ---------------------------------------------- |
| `white_noise`   | The full 6×22 board string with colour markers |
| `intensity`     | Current intensity setting                      |
| `drop_color`    | Current drop colour setting                    |
| `active_drops`  | Number of raindrops currently on the board     |

## Tips

- Use the **light** intensity for a relaxing ambient effect. It changes
  only 3 tiles per cycle, keeping the sound minimal.
- Pair with a slow refresh interval (the default page rotation) so each
  frame lingers before the next gentle shift.
