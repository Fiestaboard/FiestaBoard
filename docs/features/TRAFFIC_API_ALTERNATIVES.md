# Traffic API Alternatives and Cost Comparison

This guide compares different routing/traffic API providers to help you choose the most cost-effective solution for your needs.

## Quick Recommendation

**Use HERE Routing API** - It offers the best combination of:
- ✅ Largest free tier (250,000 requests/month)
- ✅ 90% cheaper than Google after free tier
- ✅ Enterprise-grade traffic data (used by BMW, Mercedes, Audi)
- ✅ Full support for driving (with traffic) and bicycle routing
- ✅ No credit card required for free tier

## Detailed Comparison

### 1. HERE Routing API (Recommended) ⭐

**Pricing:**
- **Free Tier:** 250,000 requests/month (no credit card required)
- **Paid:** ~$0.002 per request after free tier
- **Cost vs Google:** 90% cheaper

**Features:**
- Real-time traffic data (enterprise-grade, used by automotive industry)
- Multi-modal routing: car, bicycle, pedestrian, scooter, truck
- Traffic incidents and congestion data
- Global coverage
- Matrix API for bulk route queries
- Isoline API for reachability analysis

**Traffic Quality:** ⭐⭐⭐⭐⭐ (5/5)
- Used by major automakers (BMW, Mercedes, Audi)
- Real-time traffic from millions of connected vehicles
- Historical traffic patterns
- Traffic incidents and road closures

**Setup:**
1. Sign up at https://developer.here.com/
2. Create a project
3. Generate API key with Routing v8 permissions
4. Add to `env.example`: `HERE_API_KEY=your_key_here`

**Supported Travel Modes:**
- `car` - Driving with real-time traffic
- `bicycle` - Bicycle routing
- `pedestrian` - Walking
- `scooter` - Scooter/motorcycle
- `truck` - Truck routing with restrictions

**Documentation:** https://developer.here.com/documentation/routing-api/dev_guide/index.html

---

### 2. Google Routes API (Current Fallback)

**Pricing:**
- **Free Tier:** 10,000 requests/month (Essentials tier, as of March 2025)
- **Cost:** ~$5 per 1,000 requests after free tier
- **Monthly estimate:** 1,000 requests = **FREE** (within free tier)

**Features:**
- Excellent real-time traffic data
- Multi-modal routing: drive, bicycle, transit, walk
- Turn-by-turn directions
- Traffic-aware routing
- Route optimization

**Traffic Quality:** ⭐⭐⭐⭐⭐ (5/5)
- Industry-leading traffic data
- Real-time updates from Android devices
- Historical traffic patterns

**Pros:**
- Most accurate traffic data in many regions
- Excellent documentation
- Reliable service

**Cons:**
- ❌ Limited free tier (10,000 requests/month)
- ❌ Costs add up for high-volume usage

**Setup:**
1. Go to Google Cloud Console
2. Enable Routes API
3. Create API key
4. Add to `env.example`: `GOOGLE_ROUTES_API_KEY=your_key_here`

---

### 3. TomTom Routing API

**Pricing:**
- **Free Tier:** 2,500 requests/day (~75,000/month)
- **Paid:** ~$0.0033 per request
- **Cost vs Google:** 80% cheaper

**Features:**
- Real-time traffic data
- Multi-modal routing: car, bicycle, pedestrian, motorcycle, truck
- Traffic flow and incidents
- Global coverage

**Traffic Quality:** ⭐⭐⭐⭐ (4/5)
- Good traffic data in major markets
- Real-time updates
- Historical patterns

**Pros:**
- Good free tier
- Competitive pricing
- Reliable service

**Cons:**
- Smaller free tier than HERE
- Traffic quality varies by region

**Setup:**
1. Sign up at https://developer.tomtom.com/
2. Create application
3. Get API key
4. Would require code changes to integrate (not currently supported)

**Documentation:** https://developer.tomtom.com/routing-api/documentation

---

### 4. Mapbox Directions API

**Pricing:**
- **Free Tier:** 100,000 requests/month
- **Paid:** $0.001-0.005 per request (tiered pricing)
- **Cost vs Google:** 50-90% cheaper

**Features:**
- Traffic-aware routing
- Multi-modal: driving, cycling, walking
- Matrix API for bulk queries
- Isochrone API

**Traffic Quality:** ⭐⭐⭐⭐ (4/5)
- Good traffic data in major markets
- Real-time updates
- Historical patterns

**Pros:**
- Good free tier
- Competitive pricing
- Excellent developer experience

**Cons:**
- Traffic data not as comprehensive as Google/HERE
- Better for general routing than traffic-specific use cases

**Setup:**
1. Sign up at https://www.mapbox.com/
2. Get access token
3. Would require code changes to integrate (not currently supported)

**Documentation:** https://docs.mapbox.com/api/navigation/directions/

---

### 5. Google Distance Matrix API (Alternative Google Option)

**Pricing:**
- **Free Tier:** None
- **Cost:** $0.005-0.01 per element (50% cheaper than Routes API)
- **Monthly estimate:** 1,000 requests = $5-10

**Features:**
- Travel time with traffic
- Distance calculation
- Multi-modal support
- Simpler than Routes API

**Traffic Quality:** ⭐⭐⭐⭐⭐ (5/5)
- Same traffic data as Routes API

**Pros:**
- 50% cheaper than Routes API
- Sufficient for simple travel time queries
- No turn-by-turn directions (which you don't need)

**Cons:**
- Still expensive compared to HERE/TomTom/Mapbox
- No free tier

**Note:** Could be implemented as an alternative Google provider if needed.

---

## Cost Comparison Table

Based on 1,440 requests/month (with caching enabled):

| Provider | Free Tier | Cost/Request | Monthly Cost | Savings vs Google |
|----------|-----------|--------------|--------------|-------------------|
| **HERE** (recommended) | 250k/month | $0.001 | **$0** (free) | **100%** |
| Google Routes | 10k/month | ~$0.005 | **$0** (free) | 0% (baseline) |
| Google Distance Matrix | 10k/month | ~$0.005 | **$0** (free) | 0% |
| TomTom | 75k/month | ~$0.00075 | **$0** (free) | **100%** |
| Mapbox | 100k/month | $0.002 | **$0** (free) | **100%** |

**Without caching** (8,640 requests/month):

| Provider | Monthly Cost | Savings vs Google |
|----------|--------------|-------------------|
| **HERE** | **$0** (free) | **100%** |
| Google Routes | **$0** (within 10k free tier) | 0% (baseline) |
| Google Distance Matrix | **$0** (within 10k free tier) | 0% |
| TomTom | **$0** (free) | **100%** |
| Mapbox | **$0** (free) | **100%** |

## Migration Guide

### Switching from Google to HERE

The system is already configured to use HERE as the primary provider with Google as fallback.

**Steps:**
1. Get a free HERE API key (see setup above)
2. Update your configuration:
   ```bash
   HERE_API_KEY=your_here_api_key
   TRAFFIC_API_PROVIDER=here
   TRAFFIC_CACHE_ENABLED=true
   ```
3. Restart the service
4. Monitor logs to ensure HERE is working
5. Keep Google key as fallback for reliability

**Expected Results:**
- 100% cost reduction (within free tier)
- Same traffic quality
- Automatic fallback to Google if HERE fails

### Testing Different Providers

To test a different provider:

1. Set `TRAFFIC_API_PROVIDER=google` to test Google
2. Set `TRAFFIC_API_PROVIDER=here` to test HERE
3. Monitor logs for API calls and cache hits
4. Compare traffic times for accuracy

## Monitoring API Usage

### Check Cache Statistics

The system logs cache performance:
- Cache hits vs misses
- API calls made
- Hit rate percentage

Look for log messages like:
```
Cache HIT: here_DRIVE_abc123 (age: 120s)
Cache MISS: here_DRIVE_xyz789
```

### HERE API Dashboard

Monitor usage at: https://platform.here.com/admin/apps

### Google Cloud Console

Monitor usage at: https://console.cloud.google.com/apis/dashboard

## Best Practices

1. **Enable Caching** (default: enabled)
   - Reduces API calls by 83-92%
   - Set `TRAFFIC_CACHE_ENABLED=true`

2. **Adjust Cache TTL** based on needs:
   - 300s (5 min) - Good balance (default)
   - 600s (10 min) - More savings, slightly stale data
   - 180s (3 min) - Fresher data, more API calls

3. **Use HERE as Primary**
   - Free tier covers most use cases
   - Keep Google as fallback for reliability

4. **Monitor Rate Limits**
   - System warns at 80% of hourly limit
   - Blocks requests at 100% to prevent overages

5. **Set Appropriate Refresh Intervals**
   - 300s (5 min) recommended for traffic pages
   - Longer intervals for less time-sensitive routes

## Troubleshooting

### HERE API Not Working

Check logs for errors:
- `401 Unauthorized` - Invalid API key
- `403 Forbidden` - API key lacks permissions
- `400 Bad Request` - Invalid location format

System automatically falls back to Google if HERE fails.

### High API Costs

1. Verify caching is enabled: `TRAFFIC_CACHE_ENABLED=true`
2. Check cache hit rate in logs
3. Increase cache TTL if acceptable
4. Ensure you're using HERE (free tier)
5. Review page refresh intervals

### Traffic Data Inaccurate

1. Compare HERE vs Google results
2. Check time of day (traffic varies)
3. Verify location format (address vs lat,lng)
4. Ensure travel mode is correct

## Support

- **HERE Support:** https://developer.here.com/help
- **Google Support:** https://console.cloud.google.com/support
- **Fiesta Issues:** https://github.com/your-repo/issues

