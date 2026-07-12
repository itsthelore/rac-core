//! Per-response character budget (ADR-033) — a port of `src/rac/mcp/budget.py`
//! (ORACLE-NEXT revision, which adds the `items` rule). Shared by the CLI
//! retrieve surface (`commands::cmd_retrieve`) and the rac-mcp server.
//!
//! The budget unit is CHARACTERS (Python `len` of the serialized string —
//! Unicode code points, not bytes) of the payload serialized as
//! `json.dumps(payload, ensure_ascii=False)` with DEFAULT separators — i.e.
//! `", "` / `": "` WITH spaces (`pyjson::dumps_compact`). The docstring in the
//! oracle says "no spaces"; the code does not pass `separators`, so the wire
//! truth is *with* spaces (PORT-CONTRACT.d/10 §2) — port the code, not the
//! comment.
//!
//! Rule order (first matching key wins): `matches` → `incoming` → `items` →
//! `content` → mark-only (summary). Two overrun behaviors are ported
//! bug-for-bug (PORT-CONTRACT.d/10 §6):
//! - `get_summary` has no truncatable field: an over-budget summary is
//!   marked (`truncated:true, omitted:0, HINT_SUMMARY`) but nothing is
//!   dropped — the payload stays over budget.
//! - `get_related` with `depth>1`: only `incoming` shrinks; `neighborhood`
//!   is not truncatable, so the response can massively exceed the budget
//!   while carrying the marker.

use crate::pyjson::dumps_compact;
use serde_json::{json, Map, Value};

pub const DEFAULT_BUDGET: i64 = 10_000;

pub const MARKER_TRUNCATED: &str = "truncated";
pub const MARKER_OMITTED: &str = "omitted";
pub const MARKER_HINT: &str = "hint";

pub const HINT_SEARCH: &str = "Narrow the query or request a specific artifact ID.";
pub const HINT_RELATED: &str = "Request the artifact directly, or narrow what you are changing.";
pub const HINT_CONTENT: &str =
    "Request a more specific artifact, or read the file directly for the full content.";
pub const HINT_SUMMARY: &str = "The repository summary exceeds the response budget; raise the \
server budget to see the full overview.";
pub const HINT_RETRIEVE: &str = "Lower top_k, raise the budget, or narrow the task.";

/// `len(text)` in Python — code points, not bytes.
pub fn char_len(s: &str) -> i64 {
    s.chars().count() as i64
}

/// `text[:stop]` with Python slice semantics (negative stop trims the tail;
/// the truncators only pass non-negative stops, but the retrieve excerpt
/// share can go negative).
pub fn py_slice_to(s: &str, stop: i64) -> String {
    let n = char_len(s);
    let stop = if stop < 0 { (n + stop).max(0) } else { stop.min(n) };
    s.chars().take(stop as usize).collect()
}

fn length(payload: &Value) -> i64 {
    char_len(&dumps_compact(payload))
}

/// `budget.serialize(payload, budget)`.
pub fn serialize(payload: &Value, budget: i64) -> String {
    let text = dumps_compact(payload);
    if char_len(&text) <= budget {
        return text;
    }
    dumps_compact(&truncate(payload, budget))
}

fn truncate(payload: &Value, budget: i64) -> Value {
    let obj = payload.as_object().expect("payload is an object");
    if obj.contains_key("matches") {
        return truncate_list(payload, "matches", budget, HINT_SEARCH);
    }
    if obj.contains_key("incoming") {
        return truncate_list(payload, "incoming", budget, HINT_RELATED);
    }
    if obj.contains_key("items") {
        return truncate_items(payload, budget);
    }
    if obj.contains_key("content") {
        return truncate_content(payload, budget);
    }
    // No truncatable field (get_summary): mark, drop nothing (overrun #1).
    let mut marked = obj.clone();
    marked.insert(MARKER_TRUNCATED.to_string(), json!(true));
    marked.insert(MARKER_OMITTED.to_string(), json!(0));
    marked.insert(MARKER_HINT.to_string(), json!(HINT_SUMMARY));
    Value::Object(marked)
}

/// A copy of `payload` with `key` replaced by `kept` and the marker added.
/// `IndexMap::insert` keeps an existing key's position, matching Python
/// dict-update semantics (a `truncated` key already present — the
/// `get_related` edge-overflow marker — is overwritten in place).
fn with_marker(payload: &Value, key: &str, kept: Vec<Value>, omitted: i64, hint: &str) -> Value {
    let mut marked: Map<String, Value> = payload.as_object().expect("object").clone();
    marked.insert(key.to_string(), Value::Array(kept));
    marked.insert(MARKER_TRUNCATED.to_string(), json!(true));
    marked.insert(MARKER_OMITTED.to_string(), json!(omitted));
    marked.insert(MARKER_HINT.to_string(), json!(hint));
    Value::Object(marked)
}

fn truncate_list(payload: &Value, key: &str, budget: i64, hint: &str) -> Value {
    let items: Vec<Value> = payload[key].as_array().cloned().unwrap_or_default();
    let total = items.len() as i64;
    let mut kept = items;
    while !kept.is_empty() {
        let candidate = with_marker(payload, key, kept.clone(), total - kept.len() as i64, hint);
        if length(&candidate) <= budget {
            return candidate;
        }
        kept.pop();
    }
    with_marker(payload, key, Vec::new(), total, hint)
}

fn truncate_content(payload: &Value, budget: i64) -> Value {
    let content = payload["content"].as_str().unwrap_or("").to_string();
    let total = char_len(&content);
    let with_content = |kept: String, omitted: i64| -> Value {
        let mut marked: Map<String, Value> = payload.as_object().expect("object").clone();
        marked.insert("content".to_string(), json!(kept));
        marked.insert(MARKER_TRUNCATED.to_string(), json!(true));
        marked.insert(MARKER_OMITTED.to_string(), json!(omitted));
        marked.insert(MARKER_HINT.to_string(), json!(HINT_CONTENT));
        Value::Object(marked)
    };
    let (mut lo, mut hi) = (0i64, total);
    let mut best = 0i64;
    while lo <= hi {
        let mid = (lo + hi).div_euclid(2);
        let candidate = with_content(py_slice_to(&content, mid), total - mid);
        if length(&candidate) <= budget {
            best = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    with_content(py_slice_to(&content, best), total - best)
}

/// The retrieve `items` rule (ADR-113): excerpt-first, then whole-item.
fn truncate_items(payload: &Value, budget: i64) -> Value {
    let items: Vec<Value> = payload["items"].as_array().cloned().unwrap_or_default();
    let total = items.len() as i64;
    let mut kept = items;
    while !kept.is_empty() {
        let omitted = total - kept.len() as i64;
        let candidate = with_marker(payload, "items", kept.clone(), omitted, HINT_RETRIEVE);
        if length(&candidate) <= budget {
            return candidate;
        }
        // Trim the last kept item's excerpt before dropping it entirely.
        let mut last = kept
            .last()
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let excerpt: String = last
            .get("excerpt")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let (mut lo, mut hi) = (0i64, char_len(&excerpt));
        let mut best: Option<i64> = None;
        while lo <= hi {
            let mid = (lo + hi).div_euclid(2);
            last.insert("excerpt".to_string(), json!(py_slice_to(&excerpt, mid)));
            let mut trial_items: Vec<Value> = kept[..kept.len() - 1].to_vec();
            trial_items.push(Value::Object(last.clone()));
            let trial = with_marker(payload, "items", trial_items, omitted, HINT_RETRIEVE);
            if length(&trial) <= budget {
                best = Some(mid);
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        if let Some(best) = best {
            last.insert("excerpt".to_string(), json!(py_slice_to(&excerpt, best)));
            let mut final_items: Vec<Value> = kept[..kept.len() - 1].to_vec();
            final_items.push(Value::Object(last));
            return with_marker(payload, "items", final_items, omitted, HINT_RETRIEVE);
        }
        kept.pop();
    }
    with_marker(payload, "items", Vec::new(), total, HINT_RETRIEVE)
}
