//! CommonMark -> HTML rendering for `export` `body_html`, byte-matching
//! markdown-it-py 4.2.0's `"commonmark"` preset with `{"html": False}`.
//!
//! The commonmark preset pins `xhtmlOut: true` (`<hr />`, `<br />`),
//! `langPrefix: "language-"`, typographer/linkify off. `html: False`
//! disables the raw-HTML block/inline rules entirely, so HTML-looking
//! source arrives as escaped text. The `markdown-it` crate's `cmark`
//! plugin set matches that rule set exactly when the `html` plugin is
//! not installed; `xrender` selects the XHTML dialect.

use std::sync::OnceLock;

use markdown_it::MarkdownIt;

fn parser() -> &'static MarkdownIt {
    static PARSER: OnceLock<MarkdownIt> = OnceLock::new();
    PARSER.get_or_init(|| {
        let mut md = MarkdownIt::new();
        markdown_it::plugins::cmark::add(&mut md);
        md
    })
}

/// Render a Markdown body to HTML (raw HTML disabled -> escaped as text).
pub fn render(body: &str) -> String {
    parser().parse(body).xrender()
}
