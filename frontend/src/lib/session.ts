import { useSyncExternalStore } from 'react';

export interface AccountUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface SessionTokens {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
}

interface SessionSnapshot {
  user: AccountUser | null;
  revision: number;
}

// Deliberately never serialized to browser storage, URLs, or query data.
let tokens: SessionTokens | null = null;
let snapshot: SessionSnapshot = { user: null, revision: 0 };
const listeners = new Set<() => void>();

function publish(next: SessionSnapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const getAccessToken = (): string | undefined => tokens?.access_token;
export const getRefreshToken = (): string | undefined => tokens?.refresh_token;
export const getSessionRevision = (): number => snapshot.revision;

export function setSessionTokens(next: SessionTokens): void {
  tokens = { ...next };
}

export function setSessionUser(user: AccountUser): void {
  publish({ user, revision: snapshot.revision + (snapshot.user?.id === user.id ? 0 : 1) });
}

export function clearSession(): void {
  tokens = null;
  publish({ user: null, revision: snapshot.revision + 1 });
}

export function useSession(): SessionSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
}
