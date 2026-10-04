import { apiClient, ApiError, rotateAccessToken } from './client';
import {
  clearSession, getRefreshToken, setSessionTokens, setSessionUser,
  type AccountUser, type SessionTokens,
} from '../lib/session';

export interface LoginInput { email: string; password: string }
export interface RegisterInput extends LoginInput { full_name?: string }

async function authenticate(endpoint: '/auth/login' | '/auth/register', input: LoginInput | RegisterInput): Promise<AccountUser> {
  clearSession();
  try {
    const tokens = await apiClient.post<SessionTokens>(endpoint, input, { anonymous: true });
    if (!tokens?.access_token) throw new ApiError(200, tokens, 'The authentication response did not contain an access token.');
    setSessionTokens(tokens);
    const user = await apiClient.get<AccountUser>('/auth/me', { authenticated: true, refreshOnUnauthorized: false });
    setSessionUser(user);
    return user;
  } catch (error) {
    clearSession();
    throw error;
  }
}

export const authApi = {
  login: (input: LoginInput) => authenticate('/auth/login', input),
  register: (input: RegisterInput) => authenticate('/auth/register', input),
  me: async () => {
    const user = await apiClient.get<AccountUser>('/auth/me', { authenticated: true });
    setSessionUser(user);
    return user;
  },
  refresh: async () => {
    await rotateAccessToken();
    return authApi.me();
  },
  logout: async (): Promise<void> => {
    const refreshToken = getRefreshToken();
    try {
      if (!refreshToken) throw new ApiError(401, { detail: 'No refresh token is available for server-side revocation.' });
      await apiClient.post<void>('/auth/logout', { refresh_token: refreshToken }, { authenticated: true, refreshOnUnauthorized: false });
    } finally {
      clearSession();
    }
  },
};
