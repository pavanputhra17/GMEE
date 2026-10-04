import { useId, useState, type FormEvent } from 'react';
import { LogIn, LogOut, RefreshCw, UserRound, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/auth';
import { useSession } from '../lib/session';
import { Dialog } from './Dialog';
import { QueryError } from './QueryError';

export function AccountPanel({ signInLabel = 'Sign in' }: { signInLabel?: string }) {
  const { user } = useSession();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const id = useId();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    setNotice('');
    try {
      const input = { email: email.trim(), password };
      if (mode === 'register') await authApi.register({ ...input, ...(fullName.trim() ? { full_name: fullName.trim() } : {}) });
      else await authApi.login(input);
      setPassword('');
      setNotice('Signed in. Your identity was verified by /auth/me.');
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  };

  const logout = async () => {
    setPending(true);
    setError(null);
    try {
      await authApi.logout();
      setNotice('Signed out. In-memory credentials have been cleared.');
    } catch (failure) {
      setError(failure);
      setNotice('Local credentials cleared. Server-side logout could not be confirmed; the server session may remain active until expiry.');
    } finally {
      queryClient.removeQueries({ queryKey: ['eval'] });
      setPassword('');
      setPending(false);
    }
  };

  const refresh = async () => {
    setPending(true);
    setError(null);
    setNotice('');
    try {
      await authApi.refresh();
      setNotice('Session rotated and account re-verified. Tokens remain in memory only.');
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <button type="button" onClick={() => { setError(null); setNotice(''); setOpen(true); }} className="btn-brutal">
        <UserRound className="w-3.5 h-3.5" /> {user ? 'Account' : signInLabel}
      </button>
      {open && (
        <Dialog labelledBy={`${id}-title`} onClose={() => { if (!pending) { setOpen(false); setPassword(''); } }}>
          <div className="flex items-center justify-between gap-3">
            <h2 id={`${id}-title`} className="text-2xl font-display">GMEE Account</h2>
            <button type="button" aria-label="Close account" disabled={pending} onClick={() => { setOpen(false); setPassword(''); }} className="btn-brutal !px-2">
              <X className="w-4 h-4" />
            </button>
          </div>
          <p className="text-xs font-mono text-hermes-bone/65">Bearer and rotating refresh tokens are held in memory only. Reloading this page ends the local session; no tokens are saved in browser storage.</p>
          {error != null && <QueryError title="Account request failed" error={error} />}
          {notice && <p role="status" className="text-xs font-mono border border-hermes-bone/25 p-3">{notice}</p>}
          {user ? (
            <div className="space-y-4">
              <dl className="text-sm space-y-2">
                <div><dt className="text-hermes-bone/50 font-mono text-xs">Signed in as</dt><dd>{user.full_name || user.email}</dd></div>
                <div><dt className="text-hermes-bone/50 font-mono text-xs">Email</dt><dd>{user.email}</dd></div>
                <div><dt className="text-hermes-bone/50 font-mono text-xs">Role</dt><dd>{user.role}</dd></div>
              </dl>
              <div className="flex flex-wrap gap-3">
                <button type="button" disabled={pending} onClick={() => void refresh()} className="btn-brutal"><RefreshCw className="w-3.5 h-3.5" /> Rotate session</button>
                <button type="button" disabled={pending} onClick={() => void logout()} className="btn-brutal"><LogOut className="w-3.5 h-3.5" /> Log out</button>
              </div>
            </div>
          ) : (
            <form onSubmit={(event) => void submit(event)} className="space-y-4">
              <div className="flex gap-2" aria-label="Account action">
                <button type="button" disabled={pending} aria-pressed={mode === 'login'} onClick={() => { setMode('login'); setError(null); }} className="btn-brutal">Login</button>
                <button type="button" disabled={pending} aria-pressed={mode === 'register'} onClick={() => { setMode('register'); setError(null); }} className="btn-brutal">Register</button>
              </div>
              <div>
                <label htmlFor={`${id}-email`} className="block text-xs font-mono mb-1">Email</label>
                <input id={`${id}-email`} type="email" required autoComplete="username" value={email} disabled={pending} onChange={(event) => setEmail(event.target.value)} className="field-brutal w-full" />
              </div>
              {mode === 'register' && <div>
                <label htmlFor={`${id}-name`} className="block text-xs font-mono mb-1">Full name (optional)</label>
                <input id={`${id}-name`} autoComplete="name" value={fullName} disabled={pending} onChange={(event) => setFullName(event.target.value)} className="field-brutal w-full" />
              </div>}
              <div>
                <label htmlFor={`${id}-password`} className="block text-xs font-mono mb-1">Password</label>
                <input id={`${id}-password`} type="password" required minLength={mode === 'register' ? 10 : undefined} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} value={password} disabled={pending} onChange={(event) => setPassword(event.target.value)} aria-describedby={mode === 'register' ? `${id}-password-hint` : undefined} className="field-brutal w-full" />
                {mode === 'register' && <p id={`${id}-password-hint`} className="text-xs text-hermes-bone/55 mt-1">At least 10 characters; cannot be entirely numeric.</p>}
              </div>
              <button type="submit" disabled={pending} className="btn-brutal"><LogIn className="w-3.5 h-3.5" /> {pending ? 'Contacting account service…' : mode === 'register' ? 'Create account' : 'Log in'}</button>
            </form>
          )}
        </Dialog>
      )}
    </>
  );
}
