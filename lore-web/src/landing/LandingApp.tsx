import {
  CheckItem,
  CommandPalette,
  Panel,
  Prompt,
  TerminalFrame,
} from '../components';
import type { CommandPaletteItem } from '../components';
import lanternUrl from '../../design/lantern.png';
import { BetaSignup } from './BetaSignup';
import { CopyCommand } from './CopyCommand';
import './landing.css';

/** Scroll a page section into view and move focus to it. */
function goToSection(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ block: 'start' });
  el.focus({ preventScroll: true });
}

// The footer palette is a navigator, not a chatbot: every item is a
// real target — a section on this page or a page that exists.
const paletteItems: CommandPaletteItem[] = [
  {
    label: '90-second demo',
    hint: 'section',
    action: () => goToSection('demo'),
  },
  {
    label: 'MCP tools',
    hint: 'section',
    action: () => goToSection('tools'),
  },
  {
    label: 'Closed beta',
    hint: 'section',
    action: () => goToSection('beta'),
  },
  {
    label: 'Why agents do better with Lore',
    hint: 'section',
    action: () => goToSection('why'),
  },
  {
    label: 'Design system demo',
    hint: 'page',
    action: () => {
      window.location.href = './demo/';
    },
  },
  {
    label: 'Export viewer',
    hint: 'page',
    action: () => {
      window.location.href = './viewer/';
    },
  },
];

export function LandingApp() {
  return (
    <>
      <div className="landing">
        <TerminalFrame title="Lore — CLOSED BETA">
          <div className="landing__grid">
            <main className="landing__main">
              <header className="hero">
                <img
                  className="pixel-art hero__lantern"
                  src={lanternUrl}
                  width={16}
                  height={24}
                  alt="Pixel-art lantern — placeholder for the Lore lamplighter mascot"
                />
                <div className="hero__copy">
                  <h1 className="hero__title">
                    Your ADRs &amp; Decisions, Served to Your Coding Agent
                    over MCP
                  </h1>
                  <p className="hero__sub">
                    Ground every agent edit in what your team actually
                    decided.
                  </p>
                </div>
              </header>

              <section aria-labelledby="diff-heading">
                <h2 id="diff-heading" className="landing__h2">
                  What makes Lore different:
                </h2>
                <ul className="diff__list">
                  <li className="diff__item">
                    Every answer cites a decision by ID —{' '}
                    <strong className="diff__em">ADR-001</strong>, not vibes
                  </li>
                  <li className="diff__item">
                    Deterministic graph lookups —{' '}
                    <strong className="diff__em">no RAG, no embeddings</strong>,
                    no guessing
                  </li>
                  <li className="diff__item">
                    Read-only MCP server —{' '}
                    <strong className="diff__em">four tools, one command</strong>,
                    zero config
                  </li>
                </ul>
              </section>

              <section aria-labelledby="next-heading">
                <h2 id="next-heading" className="landing__h2">
                  What would you like to do next?
                </h2>
                <div className="next__list">
                  <Prompt variant="next" index={1}>
                    <a href="#demo">Run the 90-second demo.</a>
                  </Prompt>
                  <Prompt variant="next" index={2}>
                    <a href="#tools">See the four MCP tools.</a>
                  </Prompt>
                  <Prompt variant="next" index={3}>
                    <a href="#beta">Join the closed beta.</a>
                  </Prompt>
                </div>
              </section>

              <section
                id="demo"
                className="landing__section"
                tabIndex={-1}
                aria-labelledby="demo-heading"
              >
                <h2 id="demo-heading" className="landing__h2">
                  90-second demo
                </h2>
                <TerminalFrame title="lore — demo session" className="demo-slot">
                  <p className="demo-slot__text">
                    90-second demo — recording pending. This slot will hold
                    a real captured session; nothing simulated.
                  </p>
                </TerminalFrame>
              </section>

              <BetaSignup />
            </main>

            <aside className="landing__rail" aria-label="Lore at a glance">
              <h2 className="rail__heading">
                See the same prompt run twice — with and without the lore
              </h2>
              <p className="rail__note">
                Recording pending — the comparison will land in the demo
                slot.
              </p>

              <section
                id="tools"
                className="landing__section"
                tabIndex={-1}
                aria-labelledby="tools-heading"
              >
                <h3 id="tools-heading" className="rail__label">
                  MCP tools:
                </h3>
                <div className="rail__tools">
                  <Prompt command="get_summary" description="repo decision map" />
                  <Prompt
                    command="search_artifacts"
                    description="find the relevant decision"
                  />
                  <Prompt command="get_artifact" description="full record, by ID" />
                  <Prompt command="get_related" description="walk the graph" />
                </div>
                <h3 className="rail__label">and in CI:</h3>
                <Prompt
                  command="lore validate"
                  description="gate the graph on every push"
                />
              </section>

              <section
                id="why"
                className="landing__section"
                tabIndex={-1}
                aria-label="Why agents do better with Lore"
              >
                <Panel title="Why agents do better with Lore">
                  <CheckItem>
                    Citations by ID — decisions land in the diff
                  </CheckItem>
                  <CheckItem>
                    Typed Markdown + YAML, versioned with your code
                  </CheckItem>
                  <CheckItem>
                    One command:{' '}
                    <CopyCommand command="claude mcp add lore -- lore mcp" />
                  </CheckItem>
                </Panel>
              </section>
            </aside>
          </div>
        </TerminalFrame>
      </div>

      <footer aria-label="Page navigation">
        <CommandPalette
          items={paletteItems}
          prompt="lore-$"
          fixed
          ariaLabel="Navigate the page"
        />
      </footer>
    </>
  );
}
