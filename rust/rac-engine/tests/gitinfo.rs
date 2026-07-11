//! Git-recency conformance: replay `gitinfo.json` against this repo's real git
//! history. REGENERABLE — if the referenced files are re-committed, rerun
//! `rust/spec/gen_vectors_gitinfo.py` (see the vector's `regenerable` flag).

use std::fs;
use std::path::{Path, PathBuf};

use rac_engine::gitinfo::{
    last_committed, parse_iso8601_epoch, repository_root, staleness, DEFAULT_STALE_AFTER_DAYS,
};
use serde_json::Value;

fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR = rust/rac-engine; the git repo is two levels up.
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("canonicalize repo root")
}

fn vectors() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/vectors/gitinfo.json");
    let text = fs::read_to_string(&path).expect("read gitinfo.json");
    serde_json::from_str(&text).expect("parse gitinfo.json")
}

#[test]
fn recency_matches_oracle() {
    let data = vectors();
    let repo = repo_root();
    let reference_epoch = data["reference_epoch"].as_i64().unwrap();

    let root = repository_root(&repo).expect("rac-core is a git repo");

    for entry in data["paths"].as_array().unwrap() {
        let rel = entry["path"].as_str().unwrap();
        let abspath = repo.join(rel);
        let tracked = entry["tracked"].as_bool().unwrap();

        let got_last = last_committed(&root, &abspath);

        if !tracked {
            assert_eq!(got_last, None, "untracked {rel} should have no commit");
            let st = staleness(None, DEFAULT_STALE_AFTER_DAYS, reference_epoch);
            assert_eq!(st.last_committed, None);
            assert_eq!(st.age_days, None);
            assert_eq!(st.stale, None);
            continue;
        }

        // Verbatim %cI string (committer offset preserved, never normalized).
        let want_last = entry["last_committed"].as_str().unwrap();
        assert_eq!(
            got_last.as_deref(),
            Some(want_last),
            "last_committed for {rel}"
        );

        let want_age = entry["age_days"].as_i64().unwrap();
        let default_threshold = entry["default_threshold"].as_i64().unwrap();
        let want_default_stale = entry["default_stale"].as_bool().unwrap();

        let st = staleness(got_last.as_deref(), default_threshold, reference_epoch);
        assert_eq!(st.age_days, Some(want_age), "age_days for {rel}");
        assert_eq!(
            st.stale,
            Some(want_default_stale),
            "default stale for {rel}"
        );
        assert_eq!(
            st.last_committed.as_deref(),
            Some(want_last),
            "staleness keeps last_committed verbatim for {rel}"
        );

        // Boundary: strictly-greater staleness rule around the exact age.
        for b in entry["boundary"].as_array().unwrap() {
            let threshold = b["threshold"].as_i64().unwrap();
            let want_stale = b["stale"].as_bool().unwrap();
            let sb = staleness(got_last.as_deref(), threshold, reference_epoch);
            assert_eq!(
                sb.stale,
                Some(want_stale),
                "boundary threshold {threshold} for {rel}"
            );
        }
    }
}

#[test]
fn non_repo_directory_degrades_to_none() {
    // A temp dir outside any repo -> no root, all-None staleness.
    let base = std::env::var("CARGO_TARGET_TMPDIR").unwrap_or_else(|_| "/tmp".into());
    let dir = Path::new(&base).join(format!("gitinfo_norepo_{}", std::process::id()));
    fs::create_dir_all(&dir).unwrap();
    // /tmp on this box is not a git work tree; if it somehow is, skip.
    if repository_root(&dir).is_none() {
        let st = staleness(None, DEFAULT_STALE_AFTER_DAYS, 0);
        assert_eq!(st.stale, None);
    }
    fs::remove_dir_all(&dir).ok();
}

#[test]
fn iso8601_parse_offsets() {
    // UTC epoch anchors, independent of the corpus.
    assert_eq!(parse_iso8601_epoch("1970-01-01T00:00:00+00:00"), Some(0));
    assert_eq!(parse_iso8601_epoch("1970-01-01T00:00:00Z"), Some(0));
    // +01:00 means local is one hour ahead of UTC -> epoch is one hour earlier.
    assert_eq!(
        parse_iso8601_epoch("1970-01-01T01:00:00+01:00"),
        Some(0),
        "offset must be subtracted to reach UTC"
    );
    assert_eq!(
        parse_iso8601_epoch("1970-01-01T00:00:00-01:00"),
        Some(3600)
    );
    // Compact offset form.
    assert_eq!(parse_iso8601_epoch("1970-01-01T00:00:00+0000"), Some(0));
    // Fractional seconds are ignored for whole-day math.
    assert_eq!(
        parse_iso8601_epoch("1970-01-01T00:00:00.500000+00:00"),
        Some(0)
    );
    // Missing offset / garbage -> unknown.
    assert_eq!(parse_iso8601_epoch("not-a-date"), None);
    assert_eq!(parse_iso8601_epoch("1970-01-01T00:00:00"), None);
}
