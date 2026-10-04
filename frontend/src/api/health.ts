import { apiClient, ApiError, type ApiRequestOptions } from './client';

export interface HealthStatus {
  postgres?: string;
  neo4j?: string;
  redis?: string;
  status: 'ready' | 'not_ready';
}

function isReadiness(body: unknown): body is HealthStatus {
  if (!body || typeof body !== 'object' || !('status' in body)) return false;
  return (body.status === 'ready' || body.status === 'not_ready')
    && ['postgres', 'neo4j', 'redis'].every((key) =>
      !(key in body) || typeof (body as Record<string, unknown>)[key] === 'string',
    );
}

export async function fetchHealth(options?: ApiRequestOptions): Promise<HealthStatus> {
  try {
    const body = await apiClient.get<unknown>('/health/ready', options);
    if (!isReadiness(body)) throw new ApiError(200, body, 'Invalid readiness response: expected ready or not_ready.');
    return body;
  } catch (error) {
    // A readiness 503 is useful telemetry, not a lost connection. Preserve
    // healthy dependencies so a graph outage never hides Postgres-backed tabs.
    if (error instanceof ApiError && error.status === 503 && isReadiness(error.body)) return error.body;
    throw error;
  }
}
