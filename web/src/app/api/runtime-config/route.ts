import { NextRequest, NextResponse } from 'next/server';

// Support both env var names: NEXT_PUBLIC_API_URL (Next.js convention) and
// FIESTA_API_URL (set in docker-compose files on the UI container).
const ENV_API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.FIESTA_API_URL || '';

/**
 * Determine the browser-facing API URL when the backend doesn't provide one.
 * Port logic must stay in sync with the client-side fallback in lib/api.ts.
 */
function fallbackApiUrl(hostname: string): string {
  if (ENV_API_URL) return ENV_API_URL;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `http://${hostname}:8000`;
  }
  return `http://${hostname}:6969`;
}

/**
 * Runtime configuration endpoint.
 * Proxies to the backend API to discover the API URL, with sensible fallbacks.
 */
export async function GET(request: NextRequest) {
  try {
    const hostname = request.headers.get('host')?.split(':')[0] || 'localhost';

    console.log(`[Runtime Config] Request from hostname: ${hostname}`);

    const apiEndpoints = [
      'http://fiestaboard-api:8000/api/runtime-config',
      `http://${hostname}:6969/api/runtime-config`,
      'http://localhost:6969/api/runtime-config',
      'http://localhost:8000/api/runtime-config',
    ];

    for (const endpoint of apiEndpoints) {
      try {
        const response = await fetch(endpoint, {
          signal: AbortSignal.timeout(2000),
        });

        if (response.ok) {
          const data = await response.json();

          if (!data.apiUrl || data.apiUrl === '') {
            const url = fallbackApiUrl(hostname);
            console.log(`[Runtime Config] Backend returned empty apiUrl, using fallback: ${url}`);
            return NextResponse.json({ apiUrl: url });
          }

          console.log(`[Runtime Config] Returning API URL: ${data.apiUrl}`);
          return NextResponse.json(data);
        }
      } catch {
        continue;
      }
    }

    const url = fallbackApiUrl(hostname);
    console.log(`[Runtime Config] No backend reachable, using fallback: ${url}`);
    return NextResponse.json({ apiUrl: url });
  } catch (error) {
    console.error('[Runtime Config] Failed to fetch runtime config:', error);
    const hostname = request.headers.get('host')?.split(':')[0] || 'localhost';
    return NextResponse.json({ apiUrl: fallbackApiUrl(hostname) });
  }
}



