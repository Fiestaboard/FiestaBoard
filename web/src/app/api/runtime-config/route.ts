import { NextRequest, NextResponse } from 'next/server';

const ENV_API_URL = process.env.NEXT_PUBLIC_API_URL || '';

function fallbackApiUrl(hostname: string): string {
  if (ENV_API_URL) return ENV_API_URL;
  return `http://${hostname}:8000`;
}

/**
 * Runtime configuration endpoint.
 * Proxies to the backend API to discover the API URL, with sensible fallbacks.
 */
export async function GET(request: NextRequest) {
  try {
    const hostname = request.headers.get('host')?.split(':')[0] || 'localhost';

    const apiEndpoints = [
      'http://fiestaboard-api:8000/api/runtime-config',
      `http://${hostname}:8000/api/runtime-config`,
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
            return NextResponse.json({ apiUrl: fallbackApiUrl(hostname) });
          }

          return NextResponse.json(data);
        }
      } catch {
        continue;
      }
    }

    return NextResponse.json({ apiUrl: fallbackApiUrl(hostname) });
  } catch (error) {
    console.error('Failed to fetch runtime config:', error);
    const hostname = request.headers.get('host')?.split(':')[0] || 'localhost';
    return NextResponse.json({ apiUrl: fallbackApiUrl(hostname) });
  }
}



