//! Walk-order conformance: replay the oracle-generated `walk.json` vectors.
//!
//! Each case's tree is recreated in a fresh temp dir (dirs, empty files,
//! relative symlinks), walked via `find_markdown_files`, and the relative walk
//! order compared byte-for-byte to the oracle's. Regenerate the vectors with
//! `rust/spec/gen_vectors_walk.py`.

use std::fs;
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

use rac_engine::walk::{find_markdown_files, normalize_root};
use serde_json::Value;

static COUNTER: AtomicUsize = AtomicUsize::new(0);

fn vectors() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/vectors/walk.json");
    let text = fs::read_to_string(&path).expect("read walk.json");
    serde_json::from_str(&text).expect("parse walk.json")
}

fn unique_root() -> PathBuf {
    let base = std::env::var("CARGO_TARGET_TMPDIR").unwrap_or_else(|_| "/tmp".into());
    let n = COUNTER.fetch_add(1, Ordering::SeqCst);
    let dir = Path::new(&base).join(format!("walk_case_{}_{}", std::process::id(), n));
    fs::create_dir_all(&dir).expect("create case root");
    dir
}

fn str_vec(v: &Value) -> Vec<String> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_str().unwrap().to_string())
        .collect()
}

fn build_tree(root: &Path, case: &Value) {
    for d in str_vec(&case["dirs"]) {
        fs::create_dir_all(root.join(&d)).expect("mkdir");
    }
    for f in str_vec(&case["files"]) {
        let p = root.join(&f);
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent).expect("mkdir parent");
        }
        fs::write(&p, b"").expect("write file");
    }
    for link in case["symlinks"].as_array().unwrap() {
        let linkpath = root.join(link["link"].as_str().unwrap());
        if let Some(parent) = linkpath.parent() {
            fs::create_dir_all(parent).expect("mkdir link parent");
        }
        symlink(link["target"].as_str().unwrap(), &linkpath).expect("symlink");
    }
}

#[test]
fn walk_order_matches_oracle() {
    let data = vectors();
    for case in data["cases"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let recursive = case["recursive"].as_bool().unwrap();
        let expected = str_vec(&case["expected"]);

        let root = unique_root();
        build_tree(&root, case);

        let entries = find_markdown_files(root.to_str().unwrap(), recursive);
        let got: Vec<String> = entries.iter().map(|e| e.rel()).collect();

        assert_eq!(got, expected, "walk case {name}");

        // The display path must be the absolute root prefix + the relative path.
        let prefix = normalize_root(root.to_str().unwrap());
        for e in &entries {
            let want = format!("{}/{}", prefix, e.rel());
            assert_eq!(e.display, want, "display for {} in {name}", e.rel());
            assert!(e.abs.is_absolute(), "abs path absolute for {}", e.rel());
        }

        fs::remove_dir_all(&root).ok();
    }
}

#[test]
fn root_normalization_matches_oracle() {
    let data = vectors();
    for case in data["normalize"].as_array().unwrap() {
        let arg = case["arg"].as_str().unwrap();
        let expected = case["expected"].as_str().unwrap();
        assert_eq!(normalize_root(arg), expected, "normalize {arg:?}");
    }
}
