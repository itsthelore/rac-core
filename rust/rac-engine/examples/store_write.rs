//! Dev referee helper (INDEX-PLAN B2): build the derived read-model over a
//! corpus and write the store into a cache dir, printing the corpus hash.
//! Used by the batch verification to byte-compare the native store against
//! the oracle's over the live corpus. Not a product surface.

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: store_write <corpus-dir> <cache-dir>");
        std::process::exit(2);
    }
    let directory = &args[1];
    let cache_dir = std::path::Path::new(&args[2]);
    let corpus_hash = rac_engine::index_store::corpus_content_hash(directory, true);
    let derived = rac_engine::derived::build_derived_index(directory, true);
    let ok = rac_engine::index_store::write_store(
        cache_dir,
        &corpus_hash,
        rac_engine::derived::SCHEMA_VERSION,
        &derived,
    );
    if !ok {
        eprintln!("store_write: write failed");
        std::process::exit(1);
    }
    println!("{corpus_hash}");
}
