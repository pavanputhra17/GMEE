import { AccountPanel } from './AccountPanel';

export function SignInNotice({ feature }: { feature: string }) {
  return (
    <div className="border border-dashed border-hermes-bone/25 p-4 space-y-3">
      <p className="font-mono text-xs text-hermes-bone/65">Sign in to use {feature}. Requests and labels are bound to your authenticated account, not an editable annotator handle.</p>
      <AccountPanel signInLabel="Sign in to continue" />
    </div>
  );
}
