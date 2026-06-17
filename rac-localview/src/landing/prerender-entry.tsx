import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import { LandingApp } from './LandingApp';

/**
 * Server entry for the build-time prerender (scripts/prerender-landing.mjs).
 * Must render the exact tree main.tsx hydrates — StrictMode included —
 * so useId values and markup match.
 */
export function render(): string {
  return renderToString(
    <StrictMode>
      <LandingApp />
    </StrictMode>,
  );
}
