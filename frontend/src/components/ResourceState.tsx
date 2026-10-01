import { errorMessage } from "@/lib/errors";
export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="loading" role="status"><span className="loading-dots" aria-hidden="true"><i /><i /><i /></span><p>{label}</p></div>;
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  return <div className="error-panel" role="alert"><p>{errorMessage(error)}</p>{retry && <button className="button secondary" onClick={retry}>Try again</button>}</div>;
}
