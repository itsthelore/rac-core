//! The six Guide tool bodies over rac-engine's services (ADR-031: the server
//! layer owns no intelligence — it resolves, searches and shapes through the
//! same core functions the CLI uses) with stateless re-read per call
//! (ADR-032: no cache, no session state; identical repository bytes and
//! identical input produce identical output, within the ADR-033 budget).

use crate::graph;
use crate::provenance;
use rac_engine::budget::{
    serialize, HINT_RELATED, MARKER_HINT, MARKER_OMITTED, MARKER_TRUNCATED,
};
use rac_engine::output;
use rac_engine::relationships::{corpus_items, relationships_from_corpus};
use rac_engine::resolve::{
    artifact_status, build_index, find_decisions, index_from_items, resolve_in_index,
    search_index_filtered, IndexEntry, ResolvedArtifact, SearchResult, OUTCOME_RESOLVED,
};
use serde_json::{json, Map, Value};

fn opt_str(v: &Option<String>) -> Value {
    match v {
        Some(s) => json!(s),
        None => Value::Null,
    }
}

/// `errors.unreadable(id, path)`.
fn unreadable_payload(artifact_id: &str, path: &str) -> Value {
    let mut m = Map::new();
    m.insert("schema_version".to_string(), json!("1"));
    m.insert("error".to_string(), json!("unreadable"));
    m.insert("id".to_string(), json!(artifact_id));
    m.insert("path".to_string(), json!(path));
    Value::Object(m)
}

/// The MCP surfaces always include evidence
/// (`to_dict(include_evidence=True)`); the field map itself is the engine's.
fn artifact_value(m: &ResolvedArtifact) -> Map<String, Value> {
    match output::find_match_value(m, true) {
        Value::Object(obj) => obj,
        _ => unreachable!("find_match_value returns an object"),
    }
}

fn search_result_payload(result: &SearchResult) -> Value {
    output::search_result_value(result, true)
}

/// The per-call budget clamp (ADR-113): a call may only *lower* the server
/// budget; `0` (the default) is the server budget.
pub fn effective_budget(server_budget: i64, call_budget: i64) -> i64 {
    if call_budget <= 0 {
        server_budget
    } else {
        server_budget.min(call_budget)
    }
}

pub fn get_artifact(root: &str, artifact_id: &str, budget: i64) -> String {
    let entries = build_index(root, true);
    let result = resolve_in_index(&entries, artifact_id);
    let Some(artifact) = result
        .artifact
        .as_ref()
        .filter(|_| result.outcome == OUTCOME_RESOLVED)
    else {
        return serialize(&output::resolution_error_value(&result), budget);
    };
    // `None` maps to the `unreadable` structured error (ADR-034).
    let Some(content) = rac_engine::pycompat::read_text_universal(&artifact.path) else {
        return serialize(&unreadable_payload(&artifact.id, &artifact.path), budget);
    };
    let mut payload = Map::new();
    payload.insert("schema_version".to_string(), json!("1"));
    for (k, v) in artifact_value(artifact) {
        payload.insert(k, v);
    }
    let status = artifact_status(&rac_engine::parse::parse_text(&content, &artifact.path));
    let mut prov = Map::new();
    prov.insert("status".to_string(), json!(status));
    for (k, v) in provenance::artifact_provenance(root, &artifact.path) {
        prov.insert(k, v);
    }
    // Pinned key order: {schema_version, **artifact, content, provenance}.
    payload.insert("content".to_string(), json!(content));
    payload.insert("provenance".to_string(), Value::Object(prov));
    serialize(&Value::Object(payload), budget)
}

pub fn search_artifacts(
    root: &str,
    query: &str,
    artifact_type: Option<&str>,
    tags: &[String],
    live_only: bool,
    budget: i64,
) -> String {
    let entries = build_index(root, true);
    let mut result = search_index_filtered(&entries, query, artifact_type, tags, live_only);
    rac_engine::commands::annotate_search_recency(&mut result.matches, root);
    serialize(&search_result_payload(&result), budget)
}

pub fn find_decisions_tool(root: &str, topic: &str, path: Option<&str>, budget: i64) -> String {
    // Python truthiness: a non-empty `path` selects path mode.
    if let Some(p) = path.filter(|p| !p.is_empty()) {
        let payload = rac_engine::retrieve::find_decisions_path_payload(root, p);
        return serialize(&payload, budget);
    }
    let result = find_decisions(root, topic, true);
    let mut payload = search_result_payload(&result);
    payload
        .as_object_mut()
        .expect("object")
        .insert("filter".to_string(), json!("live-decisions"));
    serialize(&payload, budget)
}

pub fn get_related(root: &str, artifact_id: &str, depth: i64, budget: i64) -> String {
    // One corpus snapshot feeds resolution, outgoing, and incoming (ADR-032).
    let corpus = corpus_items(root, true);
    let entries: Vec<IndexEntry> = index_from_items(&corpus);
    let relationships = relationships_from_corpus(&corpus);
    let result = resolve_in_index(&entries, artifact_id);
    let identity_by_path: graph::IdentityByPath = entries
        .iter()
        .map(|e| {
            (
                e.path.as_str(),
                (e.id.as_str(), e.artifact_type.as_str(), e.title.as_deref()),
            )
        })
        .collect();
    let Some(artifact) = result
        .artifact
        .as_ref()
        .filter(|_| result.outcome == OUTCOME_RESOLVED)
    else {
        return serialize(&output::resolution_error_value(&result), budget);
    };
    let outgoing = graph::outgoing_references(&relationships, &artifact.path);
    let incoming_result =
        graph::incoming_references(&relationships, &identity_by_path, &artifact.path);
    let incoming: Vec<Value> = incoming_result
        .items
        .iter()
        .map(|r| {
            let mut m = Map::new();
            m.insert("id".to_string(), json!(r.id));
            m.insert("type".to_string(), json!(r.artifact_type));
            m.insert("title".to_string(), opt_str(&r.title));
            m.insert("path".to_string(), json!(r.path));
            m.insert("section".to_string(), json!(r.section));
            let mut ev = Map::new();
            ev.insert("direction".to_string(), json!("incoming"));
            ev.insert("relationship".to_string(), json!(r.section));
            ev.insert("target".to_string(), json!(r.target));
            m.insert("evidence".to_string(), Value::Object(ev));
            Value::Object(m)
        })
        .collect();
    let mut payload = Map::new();
    payload.insert("schema_version".to_string(), json!("1"));
    for (k, v) in artifact_value(artifact) {
        payload.insert(k, v);
    }
    payload.insert("outgoing".to_string(), outgoing.to_value());
    payload.insert("incoming".to_string(), Value::Array(incoming));
    let mut neighborhood_truncated = false;
    if depth > 1 {
        let hood = graph::neighborhood(&relationships, &identity_by_path, &artifact.path, depth);
        let nodes: Vec<Value> = hood
            .nodes
            .iter()
            .filter(|n| n.hops > 1)
            .map(|n| {
                let mut m = Map::new();
                m.insert("id".to_string(), json!(n.id));
                m.insert("type".to_string(), json!(n.artifact_type));
                m.insert("title".to_string(), opt_str(&n.title));
                m.insert("path".to_string(), json!(n.path));
                m.insert("hops".to_string(), json!(n.hops));
                Value::Object(m)
            })
            .collect();
        payload.insert("neighborhood".to_string(), Value::Array(nodes));
        payload.insert(
            "depth".to_string(),
            json!(depth.min(graph::MAX_TRAVERSAL_DEPTH)),
        );
        neighborhood_truncated = hood.truncated;
    }
    let edge_overflow = (incoming_result.total - incoming_result.items.len())
        + (outgoing.total - outgoing.kept());
    if edge_overflow > 0 || neighborhood_truncated {
        payload.insert(MARKER_TRUNCATED.to_string(), json!(true));
        payload.insert(MARKER_OMITTED.to_string(), json!(edge_overflow as i64));
        payload.insert(MARKER_HINT.to_string(), json!(HINT_RELATED));
    }
    serialize(&Value::Object(payload), budget)
}

pub fn get_summary(root: &str, budget: i64) -> String {
    let corpus = corpus_items(root, true);
    let p = rac_engine::portfolio::portfolio_from_corpus(root, &corpus, true);
    let mut payload = Map::new();
    payload.insert("schema_version".to_string(), json!("1"));
    payload.insert("directory".to_string(), json!(p.directory));
    payload.insert("recursive".to_string(), json!(p.recursive));
    let empty = p.total_artifacts() == 0;
    payload.insert("empty".to_string(), json!(empty));
    let mut by_type = Map::new();
    for (t, c) in &p.by_type {
        by_type.insert(t.clone(), json!(c));
    }
    let mut artifacts = Map::new();
    artifacts.insert("total".to_string(), json!(p.total_artifacts()));
    artifacts.insert("by_type".to_string(), Value::Object(by_type));
    artifacts.insert("unknown_paths".to_string(), json!(p.unknown_paths));
    payload.insert("artifacts".to_string(), Value::Object(artifacts));
    let mut validation = Map::new();
    validation.insert("valid".to_string(), json!(p.valid_artifacts));
    validation.insert("invalid".to_string(), json!(p.invalid_artifacts));
    payload.insert("validation".to_string(), Value::Object(validation));
    let mut completeness = Map::new();
    completeness.insert("recommended_slots".to_string(), json!(p.recommended_slots));
    completeness.insert("filled".to_string(), json!(p.filled_slots));
    completeness.insert(
        "ratio".to_string(),
        rac_engine::pyjson::py_float(p.completeness()),
    );
    payload.insert("completeness".to_string(), Value::Object(completeness));
    let mut relationships = Map::new();
    relationships.insert("total".to_string(), json!(p.relationships.total));
    relationships.insert("valid".to_string(), json!(p.relationships.valid));
    relationships.insert("broken".to_string(), json!(p.relationships.broken));
    relationships.insert("orphaned".to_string(), json!(p.relationships.orphaned));
    relationships.insert(
        "coverage".to_string(),
        rac_engine::pyjson::py_float(p.relationships.coverage),
    );
    payload.insert("relationships".to_string(), Value::Object(relationships));
    let attention: Vec<Value> = p
        .attention
        .iter()
        .map(|item| {
            let mut m = Map::new();
            m.insert("path".to_string(), json!(item.path));
            m.insert("identifier".to_string(), json!(item.identifier));
            m.insert("severity".to_string(), json!(item.severity));
            m.insert("code".to_string(), json!(item.code));
            m.insert("message".to_string(), json!(item.message));
            Value::Object(m)
        })
        .collect();
    payload.insert("attention".to_string(), Value::Array(attention));
    let mut health = Map::new();
    health.insert("score".to_string(), json!(p.health_score()));
    payload.insert("health".to_string(), Value::Object(health));
    let mut status = Map::new();
    status.insert("artifacts_ok".to_string(), json!(p.invalid_artifacts == 0));
    status.insert("relationships_ok".to_string(), json!(p.relationships_ok));
    status.insert(
        "ok".to_string(),
        json!(p.invalid_artifacts == 0 && p.relationships_ok),
    );
    payload.insert("validation_status".to_string(), Value::Object(status));
    if empty {
        payload.insert(
            "guidance".to_string(),
            json!(
                "This repository has no RAC artifacts yet. The user can create the \
first one with `rac quickstart`, or with `rac init` then \
`rac new <type> <path>`. Once artifacts exist, search_artifacts \
and get_artifact will return them."
            ),
        );
    }
    serialize(&Value::Object(payload), budget)
}

pub fn retrieve_grounding(
    root: &str,
    task: &str,
    scope: &str,
    top_k: i64,
    effective: i64,
    live_only: bool,
) -> String {
    // Python passes `scope or None`; the engine's own empty filter matches.
    let scope_opt = if scope.is_empty() { None } else { Some(scope) };
    let payload = rac_engine::retrieve::retrieve_grounding(
        root, task, scope_opt, top_k, effective, live_only,
    );
    serialize(&payload, effective)
}
