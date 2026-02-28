# Testing Guide: Spacecraft Launches Plugin

This plugin requires **NO API KEY** - it works out of the box with the public Launch Library 2 API.

## Quick Test (No FiestaBoard Required)

Test the API directly to verify it's working:

```bash
# Test the API endpoint directly
curl "https://ll.thespacedevs.com/2.3.0/launches/upcoming/?limit=4&mode=detailed" | jq '.results[0] | {name, net, status: .status.name}'
```

Expected output: JSON with upcoming launch data.

## Testing in FiestaBoard

### Step 1: Enable the Plugin

1. Start FiestaBoard:
   ```bash
   docker-compose up --build
   ```

2. Open web UI: http://localhost:4420

3. Go to **Integrations** page

4. Find **Spacecraft Launches** and toggle it **ON**

5. Configure (optional):
   - Max Launches: 4 (default)
   - Refresh Interval: 300 seconds (default)

6. Click **Save**

### Step 2: Create a Test Page

1. Go to **Pages** in the web UI

2. Click **Create Page**

3. Name it: "Earth Departures"

4. Add this template:

```
{center}EARTH DEPARTURES
{{spacecraft_launches.headers}}
{{spacecraft_launches.launches.0.formatted}}
{{spacecraft_launches.launches.1.formatted}}
{{spacecraft_launches.launches.2.formatted}}
{{spacecraft_launches.launches.3.formatted}}
```

5. Click **Save**

### Step 3: Verify Data

In the page editor, you should see:
- Live preview with actual launch data
- Real countdowns (updating in real-time)
- Launch names, dates, times

Example output:
```
   EARTH DEPARTURES
DATE TIME MISSION
02/28 14:30 Crew-10
03/05 08:00 Starlink 6-84
03/10 06:30 Progress MS-29
03/15 11:00 USSF-87
```

### Step 4: Test Variables

Try these template variations:

**Next Launch Countdown:**
```
{center}NEXT LAUNCH
{{spacecraft_launches.mission}}
T- {{spacecraft_launches.countdown}}
{{spacecraft_launches.rocket}}
{{spacecraft_launches.provider}}
```

**Compact List:**
```
LAUNCHES
{{spacecraft_launches.launches.0.mission}} - {{spacecraft_launches.launches.0.countdown}}
{{spacecraft_launches.launches.1.mission}} - {{spacecraft_launches.launches.1.countdown}}
{{spacecraft_launches.launches.2.mission}} - {{spacecraft_launches.launches.2.countdown}}
```

## Verification Checklist

- [ ] Plugin enables without errors
- [ ] Page preview shows real launch data
- [ ] Countdowns are computed correctly
- [ ] Data refreshes after configured interval
- [ ] No API key required
- [ ] No errors in browser console
- [ ] No errors in Docker logs

## Recording a Demo Video

### What to Show

1. **Start**: Show FiestaBoard web UI homepage
2. **Integrations**: Navigate to Integrations, show Spacecraft Launches plugin
3. **Enable**: Toggle plugin ON, show configuration (no API key fields)
4. **Save**: Click Save, show success message
5. **Create Page**: Go to Pages, create new page
6. **Template**: Add Earth Departures template
7. **Preview**: Show live preview with real launch data
8. **Variables**: Demonstrate template variables auto-completing
9. **Countdown**: Show countdown is live (changes over time)
10. **Multiple Formats**: Show 2-3 different template examples

### Recording Tools

**On Mac:**
```bash
# QuickTime Player (built-in)
# File > New Screen Recording

# Or use command line
screencapture -v earth-departures-demo.mov
```

**On Linux:**
```bash
# Using ffmpeg
ffmpeg -video_size 1920x1080 -framerate 30 -f x11grab -i :0.0 spacecraft-launches-demo.mp4

# Or use SimpleScreenRecorder (GUI)
sudo apt install simplescreenrecorder
```

**On Windows:**
```powershell
# Windows Game Bar (Win + G)
# Or use OBS Studio
```

### Narration Script

```
"Hi, I'm demonstrating the Spacecraft Launches plugin for FiestaBoard.

This plugin tracks upcoming rocket launches using the Launch Library 2 API.
No API key is required - it just works.

First, I'll enable the plugin in Integrations.
[Toggle ON, show config]

As you can see, there's no API key field - just max launches and refresh interval.

Now let's create a page to display the launches.
[Create page, add template]

Here's the Earth Departures template, inspired by airport departure boards.
[Show template]

And here's the live preview with actual launch data.
[Point to preview]

You can see real missions: Crew-10, Starlink, Progress MS-29, etc.
The countdowns are live and update in real-time.

Let me try a different format.
[Switch to countdown template]

This shows the next launch with a countdown timer.

All the data comes directly from the Launch Library API, no configuration needed.

That's the Spacecraft Launches plugin - simple, no API key, and ready to use."
```

## Troubleshooting

### No Data Showing

1. Check Docker logs:
   ```bash
   docker-compose logs -f fiestaboard-api
   ```

2. Look for errors fetching from `ll.thespacedevs.com`

3. Test API directly:
   ```bash
   curl "https://ll.thespacedevs.com/2.3.0/launches/upcoming/?limit=1"
   ```

### Rate Limit (429 Error)

- Wait 1 hour (15 requests/hour limit)
- Increase `refresh_seconds` to 600+ (10+ minutes)
- Plugin uses cached data when rate limited

### Firewall Issues

If running in restricted environment:
- Ensure `ll.thespacedevs.com` (port 443) is accessible
- Test: `curl -I https://ll.thespacedevs.com`

## Test Data Structure

The API returns this structure:

```json
{
  "results": [
    {
      "name": "Falcon 9 Block 5 | Crew-12",
      "net": "2026-03-15T14:30:00Z",
      "status": {
        "name": "Go for Launch",
        "abbrev": "Go"
      },
      "pad": {
        "name": "Space Launch Complex 40",
        "location": {"name": "Cape Canaveral, FL, USA"}
      },
      "launch_service_provider": {
        "name": "SpaceX"
      },
      "rocket": {
        "configuration": {"name": "Falcon 9"}
      },
      "mission": {
        "name": "Crew-12"
      }
    }
  ]
}
```

## API Rate Limiting

- **Free tier**: 15 requests/hour (no auth)
- **Default refresh**: 300 seconds (5 min) = 12 requests/hour ✅
- **Minimum refresh**: 240 seconds (4 min) = 15 requests/hour (at limit)

## Success Criteria

✅ Plugin works without API key
✅ Real launch data displays
✅ Countdowns compute correctly
✅ Multiple template formats work
✅ Data refreshes automatically
✅ Rate limits respected
✅ Errors handled gracefully

---

**Ready to test!** No API keys, no registration, no configuration complexity.
