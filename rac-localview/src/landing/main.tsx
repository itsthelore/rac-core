import { StrictMode } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import '../styles/base.css';
import { LandingApp } from './LandingApp';

const container = document.getElementById('root')!;
const app = (
  <StrictMode>
    <LandingApp />
  </StrictMode>
);

// Production builds prerender the landing into #root
// (scripts/prerender-landing.mjs), so hydrate the existing markup.
// In dev the root is empty; fall back to a plain client render.
if (container.firstElementChild) {
  hydrateRoot(container, app);
} else {
  createRoot(container).render(app);
}
