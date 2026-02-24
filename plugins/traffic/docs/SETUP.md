# Traffic Feature Setup Guide

## Google Routes API Setup

The Traffic feature uses Google's Routes API (v2) to get real-time travel times. Here's how to set it up properly.

### Step 1: Enable the Routes API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to **APIs & Services** → **Library**
4. Search for "**Routes API**" (NOT "Directions API" - that's the old one)
5. Click on "**Routes API**" and click **Enable**

### Step 2: Set Up Billing

⚠️ **Important**: The Routes API requires a billing account, even though it has a free tier.

1. Go to **Billing** in the Google Cloud Console
2. Link a billing account to your project
3. The Routes API includes:
   - **$200 free credit per month** (for new users)
   - First **$200 of usage free every month** (for all users)
   - After that: ~$0.005 per request

**Typical Usage Costs:**
- Checking 1 route every 5 minutes = ~8,640 requests/month = **FREE** (well under $200)
- Checking 5 routes every 5 minutes = ~43,200 requests/month = ~$16/month

### Step 3: Create an API Key

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **API Key**
3. Copy the API key
4. **Recommended**: Click "Restrict Key" to secure it:
   - Under "API restrictions", select "Restrict key"
   - Choose "Routes API" from the list
   - Under "Application restrictions", you can:
     - Leave unrestricted for Docker/local use
     - Or restrict by IP if you know your server's IP

### Step 4: Add to Your Configuration

Add the API key to your configuration:

**Option A: Via Web UI (Recommended)**
1. Open http://localhost:4420
2. Go to the **Integrations** page
3. Find **Traffic** and toggle the plugin on
4. Paste your API key in the "Google Routes API Key" field
5. Click Save

**Option B: Via Environment Variable**
Add to your `.env` file:
```bash
GOOGLE_ROUTES_API_KEY=your_api_key_here
```

### Step 5: Test It

1. In the web UI, go to the **Traffic** plugin on the **Integrations** page
2. Click "Add Route"
3. Enter:
   - **Origin**: Your home address or `40.7128,-74.0060` (coordinates work too)
   - **Destination**: Your work address or `40.7580,-73.9855`
   - **Display Name**: `WORK`
   - **Travel Mode**: Choose Drive, Bicycle, Transit, or Walk
4. Click "Validate Route"

If it works, you'll see: ✅ "Route is valid! Estimated travel time: ~X minutes"

## Troubleshooting

### Error: "403 Forbidden"

**Cause**: Routes API is not enabled or billing is not set up.

**Fix**:
1. Make sure you enabled "Routes API" (not "Directions API")
2. Verify billing is set up in Google Cloud Console
3. Wait 1-2 minutes after enabling the API

### Error: "400 Bad Request"

**Cause**: The address format is invalid or Google can't geocode it.

**Fix**:
1. Try using the full address with city and state: `123 Main St, San Francisco, CA 94102`
2. Or use coordinates: `40.7128,-74.0060`
3. Avoid ambiguous addresses like "Main Street"

### Error: "Failed to validate route"

**Possible causes**:
1. API key is incorrect
2. API key restrictions are too strict
3. Network connectivity issues

**Fix**:
1. Double-check your API key in Settings
2. Check Docker logs: `docker-compose -f docker-compose.dev.yml logs fiestaboard | grep traffic`
3. Try a different address format

### Using Coordinates Instead of Addresses

If addresses aren't working, you can use latitude,longitude coordinates:

1. Go to [Google Maps](https://maps.google.com)
2. Right-click on your location
3. Click the coordinates at the top (e.g., "40.7128, -74.0060")
4. Use this format in the Traffic settings: `40.7128,-74.0060` (no spaces)

**Example**:
- Origin: `40.7128,-74.0060` (New York City)
- Destination: `40.7580,-73.9855` (Central Park)

## Address Format Tips

### ✅ Good Address Formats

- `123 Main St, New York, NY 10001`
- `456 Park Ave, New York, NY 10022`
- `San Francisco International Airport, CA`
- `40.7128,-74.0060` (coordinates)

### ❌ Bad Address Formats

- `Main Street` (too vague)
- `Downtown` (ambiguous)
- `123` (incomplete)
- `40.7128, -74.0060` (space after comma - remove it)

## Travel Modes

The Routes API supports different travel modes:

- **🚗 Drive**: Car/driving directions with live traffic
- **🚴 Bicycle**: Bike routes (bike lanes, paths)
- **🚇 Transit**: Public transportation (bus, train, subway)
- **👣 Walk**: Walking directions

Each mode returns different routes optimized for that transportation type.

## API Limits & Quotas

- **Free tier**: $200/month in free usage
- **Rate limit**: No hard limit, but be reasonable
- **Recommended refresh**: 5-10 minutes (our default is 5 minutes)

## Privacy & Security

- Your API key is stored securely in the Docker container
- Routes API requests go directly from your server to Google
- No route data is stored permanently
- Consider using API key restrictions in production

## Need Help?

1. Check the [Google Routes API documentation](https://developers.google.com/maps/documentation/routes)
2. View your API usage in [Google Cloud Console](https://console.cloud.google.com/)
3. Check Docker logs for detailed error messages
4. Make sure you're using Routes API (v2), not the older Directions API

## Example Configuration

![Traffic Display](./traffic-display.png)

Here's a complete example for a morning commute:

**Route 1: Home to Work (Drive)**
- Origin: `1735 35th Ave, San Francisco, CA 94122`
- Destination: `525 20th St, San Francisco, CA 94107`
- Display Name: `WORK`
- Travel Mode: Drive

**Route 2: Home to Work (Bike)**
- Origin: `1735 35th Ave, San Francisco, CA 94122`
- Destination: `525 20th St, San Francisco, CA 94107`
- Display Name: `WORK-BIKE`
- Travel Mode: Bicycle

**Route 3: Home to Work (Transit)**
- Origin: `1735 35th Ave, San Francisco, CA 94122`
- Destination: `525 20th St, San Francisco, CA 94107`
- Display Name: `WORK-MUNI`
- Travel Mode: Transit

Then in your template:
```
COMMUTE OPTIONS
DRIVE: {traffic.routes.0.duration_minutes}m
BIKE: {traffic.routes.1.duration_minutes}m
MUNI: {traffic.routes.2.duration_minutes}m
```

This lets you compare all three options at a glance! 🚗🚴🚇

