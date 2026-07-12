//! The `get_related` graph view — a port of the 1-hop / bounded multi-hop
//! functions in `src/rac/services/relationships.py` (`outgoing_references`,
//! `incoming_references`, `neighborhood`) over rac-engine's resolved
//! relationship edges (ADR-031: the server shapes, core resolves).

use rac_engine::relationships::Relationship;
use rac_engine::spec::{snake, RELATIONSHIP_SECTIONS};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};

// Traversal caps (`rac.core.limits`).
pub const MAX_RELATED_EDGES: usize = 1000;
pub const MAX_TRAVERSAL_DEPTH: i64 = 5;
pub const MAX_TRAVERSAL_FRONTIER: usize = 1000;
pub const MAX_TRAVERSAL_WORK: i64 = 10_000;

/// Rank of a snake_case relationship section in the canonical order
/// (`_RELATIONSHIP_ORDER`); unknown sections rank last.
fn relationship_order(section: &str) -> usize {
    for (i, (name, _)) in RELATIONSHIP_SECTIONS.iter().enumerate() {
        if snake(name) == section {
            return i;
        }
    }
    RELATIONSHIP_SECTIONS.len()
}

/// `(id, type, title)` per path — the caller builds it from the index.
pub type IdentityByPath<'a> = HashMap<&'a str, (&'a str, &'a str, Option<&'a str>)>;

pub struct OutgoingReferences {
    /// Section (snake_case) → raw stored targets, first-seen section order.
    pub by_section: Vec<(String, Vec<String>)>,
    pub total: usize,
}

impl OutgoingReferences {
    pub fn kept(&self) -> usize {
        self.by_section.iter().map(|(_, t)| t.len()).sum()
    }

    pub fn to_value(&self) -> Value {
        let mut m = Map::new();
        for (section, targets) in &self.by_section {
            m.insert(section.clone(), json!(targets));
        }
        Value::Object(m)
    }
}

/// `outgoing_references(relationships, source_path)`.
pub fn outgoing_references(relationships: &[Relationship], source_path: &str) -> OutgoingReferences {
    let limit = MAX_RELATED_EDGES;
    let mut by_section: Vec<(String, Vec<String>)> = Vec::new();
    let mut total = 0usize;
    let mut kept = 0usize;
    for rel in relationships {
        if rel.source_path != source_path {
            continue;
        }
        total += 1;
        if kept < limit {
            match by_section.iter_mut().find(|(s, _)| *s == rel.relationship) {
                Some((_, targets)) => targets.push(rel.target.clone()),
                None => by_section.push((rel.relationship.clone(), vec![rel.target.clone()])),
            }
            kept += 1;
        }
    }
    OutgoingReferences { by_section, total }
}

pub struct IncomingReference {
    pub id: String,
    pub artifact_type: String,
    pub title: Option<String>,
    pub path: String,
    pub section: String,
    pub target: String,
}

pub struct IncomingReferences {
    pub items: Vec<IncomingReference>,
    pub total: usize,
}

/// `incoming_references(relationships, identity_by_path, target_path)`.
pub fn incoming_references(
    relationships: &[Relationship],
    identity_by_path: &IdentityByPath,
    target_path: &str,
) -> IncomingReferences {
    let limit = MAX_RELATED_EDGES;
    let mut incoming: Vec<IncomingReference> = Vec::new();
    let mut total = 0usize;
    for rel in relationships {
        if rel.resolved_path.as_deref() != Some(target_path) {
            continue;
        }
        if rel.source_path == target_path {
            continue; // self-references are not incoming edges
        }
        let Some(&(id, artifact_type, title)) = identity_by_path.get(rel.source_path.as_str())
        else {
            continue;
        };
        total += 1;
        if incoming.len() < limit {
            incoming.push(IncomingReference {
                id: id.to_string(),
                artifact_type: artifact_type.to_string(),
                title: title.map(str::to_string),
                path: rel.source_path.clone(),
                section: rel.relationship.clone(),
                target: rel.target.clone(),
            });
        }
    }
    // Decorate with the precomputed rank so the sort comparator does not
    // re-scan RELATIONSHIP_SECTIONS on every comparison; same stable sort,
    // same (rank, id, path) key.
    let mut decorated: Vec<(usize, IncomingReference)> = incoming
        .into_iter()
        .map(|r| (relationship_order(&r.section), r))
        .collect();
    decorated.sort_by(|a, b| (a.0, &a.1.id, &a.1.path).cmp(&(b.0, &b.1.id, &b.1.path)));
    IncomingReferences {
        items: decorated.into_iter().map(|(_, r)| r).collect(),
        total,
    }
}

pub struct NeighborhoodNode {
    pub id: String,
    pub artifact_type: String,
    pub title: Option<String>,
    pub path: String,
    pub hops: i64,
}

pub struct Neighborhood {
    pub nodes: Vec<NeighborhoodNode>,
    pub truncated: bool,
}

/// `neighborhood(relationships, identity_by_path, origin_path, depth=…)` —
/// the bounded BFS (v0.24 WS-D), caps from `rac.core.limits`.
pub fn neighborhood(
    relationships: &[Relationship],
    identity_by_path: &IdentityByPath,
    origin_path: &str,
    depth: i64,
) -> Neighborhood {
    let depth = depth.clamp(0, MAX_TRAVERSAL_DEPTH);

    // Undirected adjacency over resolved edges, each carrying its rank.
    let mut adjacency: HashMap<&str, Vec<(String, usize)>> = HashMap::new();
    for rel in relationships {
        let Some(resolved) = rel.resolved_path.as_deref() else {
            continue;
        };
        if rel.source_path == resolved {
            continue;
        }
        let rank = relationship_order(&rel.relationship);
        adjacency
            .entry(rel.source_path.as_str())
            .or_default()
            .push((resolved.to_string(), rank));
        adjacency
            .entry(resolved)
            .or_default()
            .push((rel.source_path.clone(), rank));
    }

    let mut visited: HashSet<String> = HashSet::new();
    visited.insert(origin_path.to_string());
    // (hops, rank, id, path) — Python tuple sort.
    let mut discovered: Vec<(i64, usize, String, String)> = Vec::new();
    let mut frontier: Vec<String> = vec![origin_path.to_string()];
    let mut work: i64 = 0;
    let mut truncated = false;

    for current_depth in 1..=depth {
        let mut next_frontier: Vec<String> = Vec::new();
        let mut sorted_frontier = frontier.clone();
        sorted_frontier.sort();
        for path in &sorted_frontier {
            // sorted(set(adjacency.get(path, []))) — dedup then sort.
            let mut neighbors: Vec<(String, usize)> = adjacency
                .get(path.as_str())
                .cloned()
                .unwrap_or_default();
            neighbors.sort();
            neighbors.dedup();
            for (neighbor_path, rank) in neighbors {
                work += 1;
                if work > MAX_TRAVERSAL_WORK {
                    truncated = true;
                    break;
                }
                if visited.contains(&neighbor_path) {
                    continue;
                }
                visited.insert(neighbor_path.clone());
                let Some(&(id, _, _)) = identity_by_path.get(neighbor_path.as_str()) else {
                    continue;
                };
                discovered.push((current_depth, rank, id.to_string(), neighbor_path.clone()));
                if next_frontier.len() >= MAX_TRAVERSAL_FRONTIER {
                    truncated = true;
                } else {
                    next_frontier.push(neighbor_path);
                }
            }
            if truncated && work > MAX_TRAVERSAL_WORK {
                break;
            }
        }
        frontier = next_frontier;
        if frontier.is_empty() {
            break;
        }
    }

    discovered.sort();
    let mut nodes: Vec<NeighborhoodNode> = discovered
        .into_iter()
        .map(|(hops, _rank, _id, path)| {
            let &(id, artifact_type, title) =
                identity_by_path.get(path.as_str()).expect("indexed path");
            NeighborhoodNode {
                id: id.to_string(),
                artifact_type: artifact_type.to_string(),
                title: title.map(str::to_string),
                path,
                hops,
            }
        })
        .collect();
    nodes.sort_by(|a, b| {
        (a.hops, &a.artifact_type, &a.id).cmp(&(b.hops, &b.artifact_type, &b.id))
    });
    Neighborhood { nodes, truncated }
}
