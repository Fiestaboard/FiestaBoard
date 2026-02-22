import { NextRequest, NextResponse } from 'next/server';

// Support both env var names: NEXT_PUBLIC_API_URL (Next.js convention) and
// FIESTA_API_URL (set in docker-compose files on the UI container).
const ENV_API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.FIESTA_API_URL || '';

/**
 * Runtime configuration endpoint (Next.js API route).
 *
 * This route is only hit in the **split-server** setup (dev / E2E) where
 * Next.js runs on port 3000 and the FastAPI backend runs on port 8000.
 *
 * In the **unified container**, nginx intercepts /api/* and proxies to the
 * backend directly, so this Next.js route is never reached.
 *
 * When we successfully probe the backend, we return the backend origin so
 * the client talks to it directly (no nginx to strip /api).
 */
export async function GET(request: NextRequest) {
  try {
    const hostname = request.headers.get('host')?.split(':')[0] || 'localhost';

    console.log(`[Runtime Config] Request from hostname: ${hostname}`);

    if (ENV_API_URL) {
      console.log(`[Runtime Config] Using env override: ${ENV_API_URL}`);
      return NextResponse.json({ apiUrl: ENV_API_URL });
    }

    const apiEndpoints = [
      { url: 'http://localhost:8000/runtime-config', origin: 'http://localhost:8000' },
      { url: `http://${hostname}:8000/runtime-config`, origin: `http://${hostname}:8000` },
    ];

    for (const { url, origin } of apiEndpoints) {
      try {
        const response = await fetch(url, {
          signal: AbortSignal.timeout(2000),
        });

        if (response.ok) {
          console.log(`[Runtime Config] Backend reachable at ${origin} (split mode)`);
          return NextResponse.json({ apiUrl: origin });
        }
      } catch {
        continue;
      }
    }

    // Backend not reachable — fall back to same-origin (unified container via nginx)
    return NextResponse.json({ apiUrl: '' });

  } catch (error) {
    console.error('Failed to fetch runtime config:', error);
    return NextResponse.json({ apiUrl: '' });
  }
}
