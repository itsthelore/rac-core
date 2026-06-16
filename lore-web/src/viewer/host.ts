/**
 * Optional editor-host bridge (RAC v0.21.7).
 *
 * When the viewer runs inside an editor webview (VS Code / Cursor),
 * `acquireVsCodeApi` is injected and this module relays the user's selection
 * to the host and applies the host's reveal requests. In a standalone Portal
 * the API is absent, every export here is inert, and the viewer behaves
 * exactly as it did before. The protocol is intentionally tiny — it carries
 * only the `path`/`id` already present in the export payload (ADR-007):
 *
 *   viewer → host : { type: "ready" }                       (on mount)
 *                   { type: "open-artifact", path, id }     (on selection)
 *   host  → viewer: { type: "reveal-artifact", id }
 */

interface HostApi {
  postMessage(message: unknown): void;
}

declare function acquireVsCodeApi(): HostApi;

let host: HostApi | null | undefined;

function getHost(): HostApi | null {
  if (host !== undefined) return host;
  // `acquireVsCodeApi` is a webview global, absent in a browser / file:// Portal.
  // It may be called only once per webview, so the result is memoised.
  host = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
  return host;
}

/** True only inside an editor webview that injected the host API. */
export function hasHost(): boolean {
  return getHost() !== null;
}

/** Announce that the viewer has mounted and can receive reveals. */
export function postReady(): void {
  getHost()?.postMessage({ type: 'ready' });
}

/** Report that the user selected an artifact, so the host can open its file. */
export function postOpenArtifact(path: string, id: string): void {
  getHost()?.postMessage({ type: 'open-artifact', path, id });
}

/**
 * Subscribe to the host's reveal requests; `onReveal(id)` runs when the host
 * asks to reveal an artifact. Returns an unsubscribe function, and is inert
 * (a no-op subscription) when there is no host.
 */
export function onRevealArtifact(onReveal: (id: string) => void): () => void {
  if (!hasHost()) return () => undefined;
  const listener = (event: MessageEvent) => {
    const data = event.data as { type?: unknown; id?: unknown } | null;
    if (data && data.type === 'reveal-artifact' && typeof data.id === 'string') {
      onReveal(data.id);
    }
  };
  window.addEventListener('message', listener);
  return () => window.removeEventListener('message', listener);
}
