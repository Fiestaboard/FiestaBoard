# Sports Scores Setup Guide

The Sports Scores feature displays recent match scores from NFL, Soccer, NHL, and NBA. Perfect for keeping track of your favorite sports at a glance.

## Overview

**What it does:**
- Display recent sports match scores
- Support for NFL, Soccer, NHL, and NBA
- Show multiple games per sport
- Automatic formatting for board display
- Optional API key for premium features

**Use Cases:**
- Check recent game scores
- Monitor multiple sports simultaneously
- Display scores on your FiestaBoard
- Keep track of favorite teams

## Prerequisites

- ✅ No API key required for basic functionality (uses free tier)
- ✅ Optional: TheSportsDB API key for premium features
- ✅ At least one sport selected (NFL, Soccer, NHL, or NBA)

## Quick Setup

### 1. Enable Sports Scores

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Sports Scores** plugin
3. Toggle the **Sports Scores** plugin on
4. Select at least one sport (NFL, Soccer, NHL, NBA)
5. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
SPORTS_SCORES_ENABLED=true
SPORTS_SCORES_SPORTS=NFL,NBA  # Comma-separated list
```

### 2. Select Sports

Choose which sports to display:

**Available Sports:**
- **NFL** - American Football
- **Soccer** - Football/Soccer
- **NHL** - Ice Hockey
- **NBA** - Basketball

You can select multiple sports. The plugin will fetch recent games for each selected sport.

### 3. (Optional) Add API Key

For premium features and higher rate limits:

1. Visit [TheSportsDB](https://www.thesportsdb.com/)
2. Sign up for a free account (or upgrade to premium)
3. Get your API key from your profile
4. Add to Settings or `.env`:

```bash
SPORTS_SCORES_API_KEY=your_api_key_here
```

**Note:** The free tier (API key "123") works for basic functionality. A premium API key provides:
- Higher rate limits
- Access to live scores
- More detailed event information

### 4. Configure Display Options

**Max Games Per Sport:**
- Default: 3 games per sport
- Range: 1-10 games
- Controls how many recent games to fetch for each sport

**Refresh Interval:**
- Default: 300 seconds (5 minutes)
- Minimum: 60 seconds
- How often to fetch new scores

### 5. Create a Page to Display Scores

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using sports score variables:

**Example Template:**
```
{center}SPORTS SCORES
{{sports_scores.games.0.formatted}}
{{sports_scores.games.1.formatted}}
{{sports_scores.games.2.formatted}}
{{sports_scores.games.3.formatted}}
```

4. **Save** and **Set as Active**

## Template Variables

### Pre-Formatted Display

Easiest way to display games with automatic formatting:

```
{{sports_scores.games.0.formatted}}
# Example output: "Patriots 24 - 17 Bills"
```

The `formatted` variable includes:
- Team names (truncated if needed)
- Scores
- Format: "Team1 Score1 - Score2 Team2"

### Individual Game Variables

Access specific games using index (0, 1, 2, etc.):

```
{{sports_scores.games.0.sport}}          # Sport name (e.g., "NFL")
{{sports_scores.games.0.team1}}          # Team 1 (e.g., "Patriots")
{{sports_scores.games.0.team2}}          # Team 2 (e.g., "Bills")
{{sports_scores.games.0.score1}}         # Score 1 (e.g., "24")
{{sports_scores.games.0.score2}}         # Score 2 (e.g., "17")
{{sports_scores.games.0.status}}         # Status (e.g., "Match Finished")
{{sports_scores.games.0.date}}           # Date (e.g., "2024-01-15")
{{sports_scores.games.0.time}}           # Time (e.g., "20:00")
{{sports_scores.games.0.formatted}}      # Formatted string
```

### Full Team Names

For longer team names, use the `_full` variants:

```
{{sports_scores.games.0.team1_full}}     # "New England Patriots"
{{sports_scores.games.0.team2_full}}     # "Buffalo Bills"
```

### Primary Game Variables

Access the first game directly (without array index):

```
{{sports_scores.sport}}                  # First game sport
{{sports_scores.team1}}                  # First game team 1
{{sports_scores.team2}}                  # First game team 2
{{sports_scores.score1}}                 # First game score 1
{{sports_scores.score2}}                 # First game score 2
{{sports_scores.formatted}}              # First game formatted
```

### Metadata

```
{{sports_scores.sport_count}}            # Number of sports selected
{{sports_scores.game_count}}             # Total number of games
{{sports_scores.last_updated}}           # Last update timestamp
```

## Example Templates

![Sports Scores Display](./sports-scores-display.png)

### Simple List

```
{center}SPORTS SCORES
{{sports_scores.games.0.formatted}}
{{sports_scores.games.1.formatted}}
{{sports_scores.games.2.formatted}}
{{sports_scores.games.3.formatted}}
{{sports_scores.games.4.formatted}}
```

Output example:
```
     SPORTS SCORES
Patriots 24 - 17 Bills
Lakers 98 - 95 Warriors
Bruins 3 - 2 Rangers
```

### By Sport

```
{center}NFL SCORES
{{sports_scores.games.0.formatted}}
{{sports_scores.games.1.formatted}}

NBA SCORES
{{sports_scores.games.2.formatted}}
{{sports_scores.games.3.formatted}}
```

### Detailed View

```
{center}SPORTS SCORES
{{sports_scores.games.0.team1}} vs {{sports_scores.games.0.team2}}
{{sports_scores.games.0.score1}} - {{sports_scores.games.0.score2}}
{{sports_scores.games.0.status}}

{{sports_scores.games.1.team1}} vs {{sports_scores.games.1.team2}}
{{sports_scores.games.1.score1}} - {{sports_scores.games.1.score2}}
```

### Compact Format

```
{center}SCORES
{{sports_scores.games.0.sport}}: {{sports_scores.games.0.formatted}}
{{sports_scores.games.1.sport}}: {{sports_scores.games.1.formatted}}
{{sports_scores.games.2.sport}}: {{sports_scores.games.2.formatted}}
```

### With Metadata

```
{center}SPORTS SCORES
{{sports_scores.sport_count}} sports
{{sports_scores.game_count}} games

{{sports_scores.games.0.formatted}}
{{sports_scores.games.1.formatted}}
{{sports_scores.games.2.formatted}}
```

## Configuration Reference

### Environment Variables

```bash
# Required
SPORTS_SCORES_ENABLED=true

# Sports (comma-separated, at least one required)
SPORTS_SCORES_SPORTS=NFL,NBA,NHL,Soccer

# Optional: API key for premium features
SPORTS_SCORES_API_KEY=your_api_key_here

# Optional: Max games per sport (default: 3)
SPORTS_SCORES_MAX_GAMES=5

# Optional: Refresh interval in seconds (default: 300)
SPORTS_SCORES_REFRESH_SECONDS=300
```

### config.json Format

```json
{
  "plugins": {
    "sports_scores": {
      "enabled": true,
      "sports": ["NFL", "NBA"],
      "api_key": "optional_key_here",
      "max_games_per_sport": 3,
      "refresh_seconds": 300
    }
  }
}
```

## Sport Selection Guide

### NFL (American Football)
- Regular season: September - January
- Playoffs: January - February
- Games typically on Sundays, Mondays, and Thursdays

### NBA (Basketball)
- Regular season: October - April
- Playoffs: April - June
- Games daily during season

### NHL (Ice Hockey)
- Regular season: October - April
- Playoffs: April - June
- Games daily during season

### Soccer
- Various leagues worldwide
- Year-round coverage
- Weekend and weekday matches

## Tips and Best Practices

### Choosing Sports

1. **Select relevant sports**: Choose sports you actually follow
2. **Limit selections**: More sports = more API calls
3. **Consider season**: Some sports are seasonal
4. **Mix and match**: Combine different sports for variety

### Max Games Per Sport

- **1-2 games**: Minimal display, fastest updates
- **3 games** (default): Good balance
- **5-10 games**: More comprehensive, slower updates

### Refresh Interval

- **60 seconds**: Very frequent updates (may hit rate limits)
- **300 seconds** (5 min, default): Good balance
- **600 seconds** (10 min): Less frequent, reduces API calls
- **1800 seconds** (30 min): Casual monitoring

**Note:** Free tier has rate limits (30 requests/minute). Adjust refresh interval accordingly.

### Display Layout

The `formatted` variable provides clean, board-friendly output:
- Team names truncated to fit display
- Scores clearly displayed
- Format: "Team1 Score1 - Score2 Team2"

## Troubleshooting

### No Games Found

**Problem:** "No games found for selected sports"

**Solutions:**
1. **Check sport selection**: Ensure at least one sport is selected
2. **Verify sport names**: Must be exactly "NFL", "Soccer", "NHL", or "NBA"
3. **Check date**: Games may not be available for past dates
4. **Try different sports**: Some sports may have limited data
5. **Check API status**: TheSportsDB may be temporarily unavailable

### Rate Limit Errors

**Problem:** Rate limit errors in logs

**Solutions:**
1. **Increase refresh interval**: Reduce frequency of API calls
2. **Reduce sports**: Fewer sports = fewer API calls
3. **Get API key**: Premium keys have higher limits
4. **Wait**: Rate limits reset after 1 minute

### Scores Not Updating

**Problem:** Scores seem stale

**Solutions:**
1. **Check refresh interval**: Verify refresh_seconds setting
2. **Check logs**: Look for API errors
3. **Test API directly**: 
   ```bash
   curl "https://www.thesportsdb.com/api/v1/json/123/searchevents.php?s=Soccer"
   ```
4. **Restart service**: May need container restart

### Invalid Sport Names

**Problem:** "Invalid sports" error

**Solutions:**
1. **Use exact names**: Must be "NFL", "Soccer", "NHL", or "NBA" (case-sensitive)
2. **Check spelling**: Common mistakes: "football" (use "NFL"), "hockey" (use "NHL")
3. **Remove duplicates**: Each sport can only be selected once

### API Key Issues

**Problem:** API key not working

**Solutions:**
1. **Verify key**: Check API key is correct
2. **Test key**: Try API directly with your key
3. **Use free tier**: Remove API key to use free tier (key "123")
4. **Check premium status**: Some features require premium subscription

## Data Source

Sports Scores uses **TheSportsDB API**:

- **API**: https://www.thesportsdb.com/
- **Free Tier**: API key "123" (30 requests/minute)
- **Premium**: Higher limits, live scores, more features
- **Coverage**: NFL, Soccer, NHL, NBA and more
- **Update Frequency**: Real-time during events

## Advanced Usage

### Combining with Other Features

```
{center}MORNING BRIEF
SPORTS
{{sports_scores.games.0.formatted}}
{{sports_scores.games.1.formatted}}

WEATHER: {{weather.temperature}}° {{weather.condition}}
TIME: {{date_time.time}}
```

### Custom Formatting

```
{center}SCORES - {{sports_scores.last_updated|slice:0:10}}
{{sports_scores.games.0.team1|pad:12}}{{sports_scores.games.0.score1}}
{{sports_scores.games.0.team2|pad:12}}{{sports_scores.games.0.score2}}
```

### Sport-Specific Display

Filter games by sport in template (requires custom logic or multiple pages).

## Related Features

- **Weather**: Complete dashboard with sports + weather
- **DateTime**: Add current time to sports display
- **Stocks**: Financial dashboard alongside sports

## Resources

- [TheSportsDB API Documentation](https://www.thesportsdb.com/documentation)
- [TheSportsDB Website](https://www.thesportsdb.com/)
- [FiestaBoard Plugin Development Guide](../../../docs/development/PLUGIN_DEVELOPMENT.md)

---

**Next Steps:**
1. Enable Sports Scores in Settings
2. Select your favorite sports (NFL, Soccer, NHL, NBA)
3. (Optional) Add API key for premium features
4. Create a page with sports scores template
5. Set as active page or combine with other data
