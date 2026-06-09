/** @deprecated Use `@/lib/api/client` instead. */
export { api as default, api } from '@/lib/api/client';
export { ApiError } from '@/lib/api/errors';

export async function httpGet<T>(path: string): Promise<T> {
  const { api } = await import('@/lib/api/client');
  return api.get<T>(path);
}
