import { NextRequest, NextResponse } from 'next/server';

// Support both env var names: NEXT_PUBLIC_API_URL (Next.js convention) and
// FIESTA_API_URL (set in docker-compose files on the UI container).
const ENV_API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.FIESTA_API_URL || '';

/**
 * Runtime configuration endpoint
 * In the unified single-container setup, API and UI run together.
 * Nginx proxies /api/* to the backend, so the UI uses same-origin requests.
 */
export async function GET(request: NextRequest) {
  try {
    const hostname = request.headers.get('host')?.split(':')[0] || 'localhost';

    console.log(`[Runtime Config] Request from hostname: ${hostname}`);
    
    // In the unified container, API is on localhost:8000
    // Nginx proxies API paths so the UI can use same-origin (empty apiUrl)
    const apiEndpoints = [
      'http://localhost:8000/api/runtime-config',        // Same container
      `http://${hostname}:8000/api/runtime-config`,      // Fallback
    ];

    for (const endpoint of apiEndpoints) {
      try {
        const response = await fetch(endpoint, {
          signal: AbortSignal.timeout(2000),
        });

        if (response.ok) {
          const data = await response.json();
          console.log(`[Runtime Config] Backend returned:`, data);
          
          // In unified container, use same-origin (empty apiUrl)
          // so all requests go through nginx which routes them correctly
          console.log(`[Runtime Config] Using same-origin (unified container)`);
          return NextResponse.json({
            apiUrl: ''
          });
        }
      } catch {
        continue;
      }
    }
    
    // If API is reachable on same origin via nginx, use empty URL
    return NextResponse.json({
      apiUrl: ''
    });
    
  } catch (error) {
    console.error('Failed to fetch runtime config:', error);
    
    // Return same-origin as default (nginx handles routing)
    return NextResponse.json({
      apiUrl: ''
    });
  }
}
