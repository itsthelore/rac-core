// Closed-beta contact address, defined once for the whole page.
// TODO(human): confirm this address before launch.
const BETA_EMAIL = 'tom@armytage.co';
const BETA_MAILTO = `mailto:${BETA_EMAIL}?subject=Lore%20closed%20beta`;

/**
 * Closed-beta signup section. Static-compatible by design: a mailto
 * link only — no form backend, no analytics, no trackers.
 */
export function BetaSignup() {
  return (
    <section
      id="beta"
      className="landing__section"
      tabIndex={-1}
      aria-labelledby="beta-heading"
    >
      <h2 id="beta-heading" className="landing__h2">
        Join the closed beta
      </h2>
      <p className="beta__copy">
        Lore is in closed beta. Request an invite:{' '}
        <a href={BETA_MAILTO}>{BETA_EMAIL}</a>
      </p>
    </section>
  );
}
