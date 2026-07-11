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

use markdown_it::parser::block::builtin::BlockParserRule;
use markdown_it::parser::core::CoreRule;
use markdown_it::parser::inline::builtin::InlineParserRule;
use markdown_it::parser::inline::InlineRoot;
use markdown_it::plugins::cmark::block::fence::CodeFence;
use markdown_it::plugins::cmark::block::heading::ATXHeading;
use markdown_it::plugins::cmark::block::lheading::SetextHeader;
use markdown_it::plugins::cmark::block::list::ListItem;
use markdown_it::plugins::cmark::block::paragraph::Paragraph;
use markdown_it::{MarkdownIt, Node};

/// markdown-it-py computes heading/lheading/paragraph token content as
/// `<lines>.strip()` — CPython `str.strip()`, whose whitespace set includes
/// `\x0b \x0c \x1c-\x1f \x85 \xa0` and more — while the markdown-it crate
/// only trims spaces/tabs around inline content. Re-strip those blocks'
/// pending inline content with Python semantics BEFORE inline parsing runs
/// (fuzz campaign 2, finding 009). Trimming shifts inline srcmaps by the
/// leading cut; nothing in the export renderer consumes inline srcmaps.
///
/// Tight lists need the same treatment via `ListItem`: markdown-it-py keeps
/// the paragraph tokens (merely hidden), so their content is still
/// `str.strip()`-ed, while the markdown-it crate SPLICES tight paragraphs'
/// children directly into the list item (`mark_tight_paragraphs`), leaving
/// `InlineRoot` nodes whose parent is the `ListItem` itself (fuzz campaign 2,
/// finding 039).
struct PyStripInlineRule;

impl CoreRule for PyStripInlineRule {
    fn run(root: &mut Node, _md: &MarkdownIt) {
        fn walk(node: &mut Node) {
            let strip_it = node.is::<ATXHeading>()
                || node.is::<SetextHeader>()
                || node.is::<Paragraph>()
                || node.is::<ListItem>();
            for child in node.children.iter_mut() {
                if strip_it {
                    if let Some(inline) = child.cast_mut::<InlineRoot>() {
                        let stripped = crate::pycompat::py_strip(&inline.content);
                        if stripped.len() != inline.content.len() {
                            inline.content = stripped.to_string();
                        }
                    }
                }
                walk(child);
            }
        }
        walk(root);
    }
}

fn parser() -> &'static MarkdownIt {
    static PARSER: OnceLock<MarkdownIt> = OnceLock::new();
    PARSER.get_or_init(|| {
        let mut md = MarkdownIt::new();
        markdown_it::plugins::cmark::add(&mut md);
        md.add_rule::<PyStripInlineRule>()
            .after::<BlockParserRule>()
            .before::<InlineParserRule>();
        md
    })
}

/// Render a Markdown body to HTML (raw HTML disabled -> escaped as text).
pub fn render(body: &str) -> String {
    let mut ast = parser().parse(body);
    if !body.ends_with('\n') {
        fix_eof_fence_content(&mut ast, body);
    }
    ast.xrender()
}

/// markdown-it-py builds fence content by SLICING the source (`src[first:
/// eMark+1]`, which silently truncates at EOF), so an UNCLOSED fence whose
/// last content line is the document's final line — in a document with no
/// trailing newline — has NO trailing `\n` in its content. The markdown-it
/// crate's `get_lines` appends `\n` unconditionally. Strip that synthetic
/// newline to match (fuzz campaign 2, finding 007).
///
/// Unclosed-at-EOF is detected structurally: the fence's source span ends at
/// EOF and holds exactly `1 + content lines` source lines (a CLOSED fence
/// spans one more line — its end marker — and its last content line then has
/// a real newline in the source). This holds inside containers too, since
/// container prefixes change line content but not line counts.
fn fix_eof_fence_content(node: &mut Node, body: &str) {
    for child in node.children.iter_mut() {
        fix_eof_fence_content(child, body);
    }
    let Some(map) = node.srcmap else { return };
    let (start, end) = map.get_byte_offsets();
    if end != body.len() {
        return;
    }
    if let Some(fence) = node.cast_mut::<CodeFence>() {
        if fence.content.ends_with('\n') {
            let span_lines = body[start..end].lines().count();
            let content_lines = fence.content.lines().count();
            if span_lines == content_lines + 1 {
                fence.content.pop();
            }
        }
    }
}
