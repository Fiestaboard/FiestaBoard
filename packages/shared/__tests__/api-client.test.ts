import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createApiClient } from '../src/api-client';

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

function mockJsonResponse(data: any, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(data),
  });
}

describe('createApiClient', () => {
  it('creates a client object with all expected methods', () => {
    const api = createApiClient('http://localhost:4420/api');
    expect(api).toBeDefined();
    expect(typeof api.getStatus).toBe('function');
    expect(typeof api.getPages).toBe('function');
    expect(typeof api.listPlugins).toBe('function');
    expect(typeof api.getSchedules).toBe('function');
    expect(typeof api.getBoardSettings).toBe('function');
    expect(typeof api.getVersion).toBe('function');
    expect(typeof api.getTemplateVariables).toBe('function');
    expect(typeof api.createPage).toBe('function');
    expect(typeof api.updatePage).toBe('function');
    expect(typeof api.deletePage).toBe('function');
    expect(typeof api.enablePlugin).toBe('function');
    expect(typeof api.disablePlugin).toBe('function');
    expect(typeof api.validateSetup).toBe('function');
    expect(typeof api.scanForBoards).toBe('function');
  });

  it('uses the provided base URL for requests', async () => {
    const api = createApiClient('http://192.168.1.50:4420/api');
    mockJsonResponse({ running: true, initialized: true });

    await api.getStatus();

    expect(mockFetch).toHaveBeenCalledWith(
      'http://192.168.1.50:4420/api/status',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      })
    );
  });

  it('handles different base URLs correctly', async () => {
    const api1 = createApiClient('/api');
    const api2 = createApiClient('https://board.example.com/api');

    mockJsonResponse({ running: true });
    await api1.getStatus();
    expect(mockFetch).toHaveBeenCalledWith('/api/status', expect.any(Object));

    mockJsonResponse({ running: true });
    await api2.getStatus();
    expect(mockFetch).toHaveBeenCalledWith('https://board.example.com/api/status', expect.any(Object));
  });

  it('throws on non-OK response', async () => {
    const api = createApiClient('/api');
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.resolve({}),
    });

    await expect(api.getStatus()).rejects.toThrow('API error: 500');
  });

  it('sends POST requests with JSON body', async () => {
    const api = createApiClient('/api');
    mockJsonResponse({ status: 'ok' });

    await api.toggleDevMode(true);

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/dev-mode',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ dev_mode: true }),
      })
    );
  });

  it('sends PUT requests with JSON body', async () => {
    const api = createApiClient('/api');
    mockJsonResponse({ status: 'ok', page: {} });

    await api.updatePage('page-123', { name: 'Updated' });

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/pages/page-123',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ name: 'Updated' }),
      })
    );
  });

  it('sends DELETE requests', async () => {
    const api = createApiClient('/api');
    mockJsonResponse({ status: 'ok' });

    await api.deletePage('page-123');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/pages/page-123',
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  it('handles query parameters correctly', async () => {
    const api = createApiClient('/api');
    mockJsonResponse({ schedules: [], total: 0, enabled: true });

    await api.getSchedules('board-1');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/schedules?board_id=board-1',
      expect.any(Object)
    );
  });

  it('handles optional target parameter on sendPage', async () => {
    const api = createApiClient('/api');
    mockJsonResponse({ status: 'ok' });

    await api.sendPage('page-1', 'board');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/pages/page-1/send?target=board',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('sends AbortSignal for renderTemplateLive', async () => {
    const api = createApiClient('/api');
    const controller = new AbortController();
    mockJsonResponse({ rendered: '', lines: [], line_count: 0, sent_to_board: false, board_id: null });

    await api.renderTemplateLive(['test'], undefined, undefined, controller.signal);

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/templates/render/live',
      expect.objectContaining({
        signal: controller.signal,
      })
    );
  });
});
