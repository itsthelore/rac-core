//! Python `json.dumps`-shaped writers over `serde_json::Value`
//! (PORT-CONTRACT.d/07 §1).
//!
//! Two dialects:
//! - [`dumps_indent2`] — `json.dumps(x, indent=2)`: bare `,` before the
//!   newline, `": "` key separator, `ensure_ascii=True` (`\uXXXX` escapes,
//!   surrogate pairs for astral), empty `[]`/`{}` inline, insertion-order
//!   keys, floats via `py_float_repr`, no trailing newline (the caller's
//!   `print` adds it).
//! - [`dumps_compact`] — the `export --documents` JSONL dialect:
//!   `json.dumps(x, ensure_ascii=False)` = separators `", "` / `": "`,
//!   raw UTF-8 for non-ASCII.
//!
//! Int vs float: a `serde_json::Number` holding an i64/u64 renders in
//! Python int form (`2`); one holding an f64 renders in float form
//! (`2.0`, `1e-05`, ...). serde_json preserves that distinction through
//! parsing (`"2"` parses integral, `"2.0"` parses as f64), and
//! `serde_json::Number::from_f64` always yields the float variant — use
//! [`py_float`] to force float form for whole values when *building*
//! payloads (e.g. a computed `2.0` must not collapse to `2`).

use crate::pycompat::py_float_repr;
use serde_json::Value;
use std::fmt::Write;

/// Build a `Value` that always serializes in Python float form (`2.0`),
/// never as an int. Panics on NaN/infinity, which `json.dumps` cannot
/// round-trip and which never occur in covered payloads.
pub fn py_float(x: f64) -> Value {
    Value::Number(serde_json::Number::from_f64(x).expect("finite float"))
}

/// `json.dumps(value, indent=2)` (ensure_ascii=True). No trailing newline.
pub fn dumps_indent2(value: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, value, true, Some(0));
    out
}

/// `json.dumps(value, indent=2, ensure_ascii=False)` — raw UTF-8 output
/// (the `rac coverage` JSON contract). No trailing newline.
pub fn dumps_indent2_no_ascii(value: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, value, false, Some(0));
    out
}

/// `json.dumps(value, ensure_ascii=False)` — compact separators
/// (`", "` item, `": "` key), raw UTF-8. No trailing newline.
pub fn dumps_compact(value: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, value, false, None);
    out
}

/// `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
/// — the canonical digest dialect (agent-rules provenance digest): keys
/// sorted (code-point order, like Python `str` `<`), no separator spaces,
/// raw UTF-8. No trailing newline.
pub fn dumps_canonical_sorted(value: &Value) -> String {
    let mut out = String::new();
    write_canonical(&mut out, value);
    out
}

fn write_canonical(out: &mut String, value: &Value) {
    match value {
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_canonical(out, item);
            }
            out.push(']');
        }
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            out.push('{');
            for (i, key) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_string(out, key, false);
                out.push(':');
                write_canonical(out, &map[key.as_str()]);
            }
            out.push('}');
        }
        other => write_value(out, other, false, None),
    }
}

fn write_value(out: &mut String, value: &Value, ensure_ascii: bool, indent: Option<usize>) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(n) => write_number(out, n),
        Value::String(s) => write_string(out, s, ensure_ascii),
        Value::Array(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(item_sep(indent));
                }
                open_line(out, indent, 1);
                write_value(out, item, ensure_ascii, indent.map(|d| d + 1));
            }
            open_line(out, indent, 0);
            out.push(']');
        }
        Value::Object(map) => {
            if map.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push('{');
            for (i, (key, item)) in map.iter().enumerate() {
                if i > 0 {
                    out.push_str(item_sep(indent));
                }
                open_line(out, indent, 1);
                write_string(out, key, ensure_ascii);
                out.push_str(": ");
                write_value(out, item, ensure_ascii, indent.map(|d| d + 1));
            }
            open_line(out, indent, 0);
            out.push('}');
        }
    }
}

/// Item separator: bare `,` with indent (newline follows), `", "` compact.
fn item_sep(indent: Option<usize>) -> &'static str {
    match indent {
        Some(_) => ",",
        None => ", ",
    }
}

/// With indent: newline plus `2 * (depth + extra)` spaces. Compact: nothing.
fn open_line(out: &mut String, indent: Option<usize>, extra: usize) {
    if let Some(depth) = indent {
        out.push('\n');
        for _ in 0..(depth + extra) * 2 {
            out.push(' ');
        }
    }
}

fn write_number(out: &mut String, n: &serde_json::Number) {
    if let Some(i) = n.as_i64() {
        out.push_str(&i.to_string());
    } else if let Some(u) = n.as_u64() {
        out.push_str(&u.to_string());
    } else {
        out.push_str(&py_float_repr(n.as_f64().expect("number is f64")));
    }
}

fn write_string(out: &mut String, s: &str, ensure_ascii: bool) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{8}' => out.push_str("\\b"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\u{c}' => out.push_str("\\f"),
            '\r' => out.push_str("\\r"),
            c if (c as u32) < 0x20 => write!(out, "\\u{:04x}", c as u32).unwrap(),
            c if ensure_ascii && (c as u32) > 0x7e => {
                // stdin surrogateescape sentinel: json.dumps writes the lone
                // surrogate itself — `\udcXX` under ensure_ascii, the raw
                // surrogate char otherwise (which stdout emission then
                // re-encodes as the original byte; keep the sentinel here).
                let cp = c as u32;
                if let Some(sur) = crate::pycompat::sentinel_surrogate(c) {
                    write!(out, "\\u{sur:04x}").unwrap();
                } else if cp <= 0xffff {
                    write!(out, "\\u{cp:04x}").unwrap();
                } else {
                    let v = cp - 0x10000;
                    let hi = 0xd800 + (v >> 10);
                    let lo = 0xdc00 + (v & 0x3ff);
                    write!(out, "\\u{hi:04x}\\u{lo:04x}").unwrap();
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn indent2_layout() {
        let v = json!({"a": [], "b": {}, "c": [1], "d": {"x": 1}});
        assert_eq!(
            dumps_indent2(&v),
            "{\n  \"a\": [],\n  \"b\": {},\n  \"c\": [\n    1\n  ],\n  \"d\": {\n    \"x\": 1\n  }\n}"
        );
    }

    #[test]
    fn ensure_ascii_split() {
        let v = json!({"u": "café 🎉"});
        assert_eq!(
            dumps_indent2(&v),
            "{\n  \"u\": \"caf\\u00e9 \\ud83c\\udf89\"\n}"
        );
        assert_eq!(dumps_compact(&v), "{\"u\": \"café 🎉\"}");
    }

    #[test]
    fn int_vs_float_form() {
        let v = json!({"i": 2, "f": py_float(2.0), "t": 1e-5});
        assert_eq!(dumps_compact(&v), "{\"i\": 2, \"f\": 2.0, \"t\": 1e-05}");
    }

    #[test]
    fn canonical_sorted_dialect() {
        // json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        let v = json!([{"title": "café — x", "identifier": "A", "category": null}]);
        assert_eq!(
            dumps_canonical_sorted(&v),
            "[{\"category\":null,\"identifier\":\"A\",\"title\":\"café — x\"}]"
        );
    }
}
