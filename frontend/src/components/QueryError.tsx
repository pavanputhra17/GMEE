import { RefreshCw } from 'lucide-react';

export function QueryError({ title, error, onRetry, retrying = false }: {
  title: string;
  error: unknown;
  onRetry?: () => unknown;
  retrying?: boolean;
}) {
  return (
    <div role="alert" className="border border-hermes-red-bright/40 bg-hermes-red-bright/5 p-3 space-y-2">
      <p className="font-mono text-xs text-hermes-red-bright">{title}</p>
      {error instanceof Error && <p className="font-mono text-xs text-hermes-bone/65 break-words">{error.message}</p>}
      {onRetry && (
        <button
          type="button"
          disabled={retrying}
          onClick={(event) => { event.stopPropagation(); void onRetry(); }}
          className="btn-brutal !py-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" /> {retrying ? 'Retrying…' : `Retry ${title.split(' unavailable')[0].toLowerCase()}`}
        </button>
      )}
    </div>
  );
}
