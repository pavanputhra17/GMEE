import type { ApiDownload } from '../api/client';

export function downloadApiResponse({ blob, filename }: ApiDownload): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  try { anchor.click(); } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}
