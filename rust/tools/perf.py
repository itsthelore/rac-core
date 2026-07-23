#!/usr/bin/env python3
"""RAC engine performance harness (stdlib only).

Measures, per configured engine, over repeated runs:
  (a) engine startup            — `<bin> --version`
  (b) single-file validate      — validate one artifact
  (c) fresh corpus walk         — validate <dir> (flag-set per engine)
  (d) cold-walk throughput      — files/s at each corpus size present
  (e) peak RSS                  — /usr/bin/time -v, getrusage fallback

  (f) search matrix              — no-cache, cold-cache, warm-cache
  (g) DECIDED_TIMING phase records  — one warm diagnostic run per query

Reports p50/p95/p99 and min/max over repeated runs. Writes plain-text and
JSON to a results dir (gitignored). Deterministic invocation env: stdio to
pipes (color off), XDG dirs pointed at a scratch dir so the oracle's usage
ping / consent writes are neutralized and no run touches the network
(PORT-CONTRACT.d/01 §5.3).

Usage:
    python3 perf.py [--config tools/perf.config.json] [--results-dir tools/.perf-results]
                    [--engines oracle,rust] [--sizes 1000,5000] [--runs N]
"""

import argparse
import json
import os
import resource
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "perf.config.json")
DEFAULT_QUERIES = (
    ("common_term", "artifact"),
    ("no_match", "zzzz-no-such-term"),
    ("multi_term", "artifact validation"),
    ("duplicate_term", "artifact artifact"),
)


def _scratch_env(scratch):
    """Env that neutralizes the oracle usage ping / consent writes."""
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = os.path.join(scratch, "state")
    env["XDG_CONFIG_HOME"] = os.path.join(scratch, "config")
    env["XDG_CACHE_HOME"] = os.path.join(scratch, "cache")
    env.pop("DECIDED_TIMING", None)
    return env


def _fmt(args, **subst):
    return [a.format(**subst) for a in args]


def _time_run(bin_path, args, env):
    """Run once, capturing stdio to pipes; return (elapsed_ms, returncode)."""
    full = [bin_path] + args
    t0 = time.perf_counter()
    proc = subprocess.run(full, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, env=env)
    dt = (time.perf_counter() - t0) * 1000.0
    return dt, proc.returncode


def _time_run_capture(bin_path, args, env):
    """Run once with captured streams for match counts and DECIDED_TIMING."""
    t0 = time.perf_counter()
    proc = subprocess.run(
        [bin_path] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True)
    dt = (time.perf_counter() - t0) * 1000.0
    return dt, proc.returncode, proc.stdout, proc.stderr


def _percentile(values, quantile):
    """Deterministic linear percentile over an already-small run sample."""
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = position - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * fraction


def _summary(times, codes):
    return {
        "runs": len(times),
        "p50_ms": round(_percentile(times, 0.50), 3),
        "p95_ms": round(_percentile(times, 0.95), 3),
        "p99_ms": round(_percentile(times, 0.99), 3),
        # Kept for compatibility with the existing evidence renderer.
        "median_ms": round(statistics.median(times), 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "returncodes": sorted(codes),
        "raw_ms": [round(t, 3) for t in times],
    }


def _measure(bin_path, args, env, runs):
    times = []
    codes = set()
    for _ in range(runs):
        dt, rc = _time_run(bin_path, args, env)
        times.append(dt)
        codes.add(rc)
    return _summary(times, codes)


def _measure_query(bin_path, args, env, runs, cache_dir, mode):
    times = []
    codes = set()
    query_env = dict(env)
    query_env["DECIDED_CACHE_DIR"] = cache_dir
    for _ in range(runs):
        if mode == "cold_cache":
            shutil.rmtree(cache_dir, ignore_errors=True)
        dt, rc = _time_run(bin_path, args, query_env)
        times.append(dt)
        codes.add(rc)
    return _summary(times, codes)


def _tree_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _first_artifact_id(corpus_dir):
    path = _pick_single_file(corpus_dir)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as fh:
            for line in fh:
                if line.startswith("id:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def _parse_timing(stderr):
    """Parse numeric, content-free `rac-timing:` records."""
    records = []
    for line in stderr.splitlines():
        if not line.startswith("rac-timing: "):
            continue
        record = {}
        for field in line[len("rac-timing: "):].split():
            if "=" not in field:
                continue
            key, value = field.split("=", 1)
            if key == "op":
                record[key] = value
                continue
            try:
                record[key] = float(value) if "." in value else int(value)
            except ValueError:
                # Legacy scorecard fields may be non-numeric in future; omit
                # rather than copying unexpected text into benchmark evidence.
                continue
        if record:
            records.append(record)
    return records


def _peak_rss_kib(bin_path, args, env):
    """Peak RSS (KiB) for one run. Prefer /usr/bin/time -v, else getrusage."""
    if os.path.exists("/usr/bin/time"):
        proc = subprocess.run(
            ["/usr/bin/time", "-v", bin_path] + args,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env=env, text=True)
        for line in proc.stderr.splitlines():
            if "Maximum resident set size" in line:
                try:
                    return int(line.rsplit(":", 1)[1].strip()), "usr-bin-time"
                except ValueError:
                    break
    # Fallback: getrusage(RUSAGE_CHILDREN) delta; ru_maxrss is KiB on Linux.
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    subprocess.run([bin_path] + args, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, env=env)
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # RUSAGE_CHILDREN is a high-water mark across all children; use `after`
    # as the peak observed after this child (best-effort without time -v).
    # Linux reports KiB; macOS reports bytes.
    peak = max(after, before)
    if sys.platform == "darwin":
        peak //= 1024
    return peak, "getrusage-children"


def _pick_single_file(corpus_dir):
    for root, _dirs, files in os.walk(corpus_dir):
        for f in sorted(files):
            if f.endswith(".md"):
                return os.path.join(root, f)
    return None


def _count_md(corpus_dir):
    n = 0
    for _root, _dirs, files in os.walk(corpus_dir):
        n += sum(1 for f in files if f.endswith(".md"))
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="RAC engine perf harness.")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--results-dir", default=os.path.join(HERE, ".perf-results"))
    ap.add_argument("--engines", default=None, help="comma list subset")
    ap.add_argument("--sizes", default=None, help="comma list subset")
    ap.add_argument("--runs", type=int, default=None, help="override run count")
    ap.add_argument(
        "--contexts", default="outside-git",
        help="comma list: outside-git,inside-git (default: outside-git)")
    args = ap.parse_args(argv)

    with open(args.config, encoding="utf-8") as fh:
        cfg = json.load(fh)

    engines = cfg["engines"]
    if args.engines:
        want = set(args.engines.split(","))
        engines = {k: v for k, v in engines.items() if k in want}

    corpora = cfg["corpora"]
    if args.sizes:
        want = set(args.sizes.split(","))
        corpora = {k: v for k, v in corpora.items() if k in want}

    runs_cfg = cfg.get("runs", {"default": 7, "20000": 3})
    scratch = os.path.join(args.results_dir, "_scratch")
    os.makedirs(scratch, exist_ok=True)
    for sub in ("state", "config", "cache"):
        os.makedirs(os.path.join(scratch, sub), exist_ok=True)
    env = _scratch_env(scratch)
    requested_contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]
    unknown_contexts = set(requested_contexts) - {"outside-git", "inside-git"}
    if unknown_contexts:
        ap.error("unknown contexts: " + ", ".join(sorted(unknown_contexts)))

    def runs_for(size):
        if args.runs:
            return args.runs
        return int(runs_cfg.get(str(size), runs_cfg.get("default", 7)))

    # Resolve corpus dirs (relative to repo/tools) and existence + counts.
    present = {}
    corpus_root = os.environ.get("DECIDED_PERF_CORPUS_ROOT")
    for size, path in corpora.items():
        if corpus_root:
            p = os.path.join(corpus_root, "c" + str(size))
        else:
            p = path if os.path.isabs(path) else os.path.join(HERE, path)
        if os.path.isdir(p):
            present[size] = {"dir": p, "count": _count_md(p)}

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": os.path.abspath(args.config),
        "corpora": {s: {"dir": v["dir"], "count": v["count"]}
                    for s, v in present.items()},
        "engines": {},
    }

    smallest = None
    if present:
        smallest = min(present, key=lambda s: present[s]["count"])

    for ename, ecfg in engines.items():
        override = "DECIDED_PERF_" + ename.upper().replace("-", "_") + "_BIN"
        bin_path = os.environ.get(override, ecfg["bin"])
        if not os.path.isabs(bin_path):
            local = os.path.abspath(os.path.join(HERE, bin_path))
            if os.path.exists(local):
                bin_path = local
        if not os.path.exists(bin_path):
            resolved = shutil.which(bin_path)
            if resolved:
                bin_path = resolved
        if not os.path.exists(bin_path):
            results["engines"][ename] = {"skipped": f"binary not found: {ecfg['bin']}"}
            continue

        edata = {"bin": bin_path, "measures": {}}

        # (a) startup
        edata["measures"]["startup"] = _measure(
            bin_path, _fmt(ecfg["version"]), env, runs_for("default"))

        # (b) single-file validate (from smallest corpus)
        if smallest:
            f = _pick_single_file(present[smallest]["dir"])
            if f:
                edata["measures"]["single_validate"] = _measure(
                    bin_path, _fmt(ecfg["single_validate"], file=f),
                    env, runs_for("default"))

        # (c)+(d) cold corpus walk + throughput per size
        walks = {}
        for size in sorted(present, key=lambda s: present[s]["count"]):
            info = present[size]
            m = _measure(bin_path, _fmt(ecfg["walk"], dir=info["dir"]),
                         env, runs_for(size))
            median_s = m["median_ms"] / 1000.0
            m["files"] = info["count"]
            m["throughput_files_per_s"] = (
                round(info["count"] / median_s, 1) if median_s > 0 else None)
            walks[size] = m
        edata["measures"]["walk"] = walks

        # (e) peak RSS at each present size (single run each)
        rss = {}
        for size in sorted(present, key=lambda s: present[s]["count"]):
            info = present[size]
            kib, method = _peak_rss_kib(
                bin_path, _fmt(ecfg["walk"], dir=info["dir"]), env)
            rss[size] = {"peak_rss_kib": kib,
                         "peak_rss_mib": round(kib / 1024.0, 1),
                         "method": method, "files": info["count"]}
        edata["measures"]["peak_rss"] = rss

        # (f)+(g) query/cache matrix. Engines without a `find` template keep
        # the historical walk-only harness behavior.
        if "find" in ecfg:
            search = {}
            for size in sorted(present, key=lambda s: present[s]["count"]):
                info = present[size]
                contexts = {}
                if "outside-git" in requested_contexts:
                    outside = os.path.join(scratch, "outside-git", str(size))
                    shutil.rmtree(outside, ignore_errors=True)
                    shutil.copytree(info["dir"], outside)
                    contexts["outside-git"] = outside
                if "inside-git" in requested_contexts:
                    contexts["inside-git"] = info["dir"]
                size_data = {}
                for context_name, corpus_dir in contexts.items():
                    exact_id = _first_artifact_id(corpus_dir)
                    identity_queries = []
                    if exact_id:
                        identity_queries = [
                            ("exact_id_search", exact_id),
                            ("rare_term", exact_id.rsplit("-", 1)[-1]),
                        ]
                    queries = identity_queries + list(DEFAULT_QUERIES)
                    context_data = {}
                    for query_name, query in queries:
                        command = _fmt(ecfg["find"], query=query, dir=corpus_dir)
                        mode_data = {}
                        base = os.path.join(
                            scratch, "query-cache", ename, str(size),
                            context_name, query_name)

                        no_cache_env = dict(env)
                        no_cache_env["DECIDED_NO_CACHE"] = "1"
                        mode_data["no_cache"] = _measure(
                            bin_path, command, no_cache_env, runs_for(size))

                        mode_data["cold_cache"] = _measure_query(
                            bin_path, command, env, runs_for(size), base, "cold_cache")

                        shutil.rmtree(base, ignore_errors=True)
                        warm_env = dict(env)
                        warm_env["DECIDED_CACHE_DIR"] = base
                        _time_run(bin_path, command, warm_env)  # unmeasured prime
                        mode_data["warm_cache"] = _measure_query(
                            bin_path, command, env, runs_for(size), base, "warm_cache")

                        timed_env = dict(warm_env)
                        timed_env["DECIDED_TIMING"] = "1"
                        _dt, rc, stdout, stderr = _time_run_capture(
                            bin_path, command, timed_env)
                        try:
                            payload = json.loads(stdout)
                            match_count = len(payload.get("matches", []))
                        except (json.JSONDecodeError, AttributeError):
                            match_count = None
                        mode_data["diagnostic"] = {
                            "returncode": rc,
                            "match_count": match_count,
                            "index_bytes": _tree_size(base),
                            "timing": _parse_timing(stderr),
                        }
                        context_data[query_name] = mode_data
                    size_data[context_name] = context_data
                search[size] = size_data
            edata["measures"]["search"] = search

        results["engines"][ename] = edata

    os.makedirs(args.results_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = os.path.join(args.results_dir, f"perf-{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
        fh.write("\n")

    txt = _render_text(results)
    txt_path = os.path.join(args.results_dir, f"perf-{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(txt)

    latest_json = os.path.join(args.results_dir, "perf-latest.json")
    latest_txt = os.path.join(args.results_dir, "perf-latest.txt")
    shutil.copyfile(json_path, latest_json)
    shutil.copyfile(txt_path, latest_txt)

    sys.stdout.write(txt)
    sys.stderr.write(f"\nJSON: {json_path}\nText: {txt_path}\n")


def _render_text(results):
    out = []
    out.append("RAC engine perf harness")
    out.append(f"generated: {results['generated_at']}")
    out.append("corpora:")
    for s, v in results["corpora"].items():
        out.append(f"  {s:>6}: {v['count']} files  ({v['dir']})")
    out.append("")
    for ename, edata in results["engines"].items():
        if "skipped" in edata:
            out.append(f"[{ename}] SKIPPED — {edata['skipped']}")
            out.append("")
            continue
        out.append(f"[{ename}]  bin={edata['bin']}")
        m = edata["measures"]
        if "startup" in m:
            s = m["startup"]
            out.append(f"  startup (--version)   median {s['median_ms']:>8.1f} ms  "
                       f"min {s['min_ms']:>8.1f} ms  (n={s['runs']}, rc={s['returncodes']})")
        if "single_validate" in m:
            s = m["single_validate"]
            out.append(f"  single-file validate  median {s['median_ms']:>8.1f} ms  "
                       f"min {s['min_ms']:>8.1f} ms  (n={s['runs']}, rc={s['returncodes']})")
        out.append("  cold corpus walk:")
        for size, w in m.get("walk", {}).items():
            out.append(
                f"    {size:>6} ({w['files']:>5} files)  "
                f"median {w['median_ms']:>9.1f} ms  min {w['min_ms']:>9.1f} ms  "
                f"=> {w['throughput_files_per_s']:>8} files/s  (n={w['runs']}, rc={w['returncodes']})")
        out.append("  peak RSS:")
        for size, r in m.get("peak_rss", {}).items():
            out.append(f"    {size:>6} ({r['files']:>5} files)  "
                       f"{r['peak_rss_mib']:>8.1f} MiB  ({r['method']})")
        if m.get("search"):
            out.append("  search matrix (p50 / p95 / p99 ms):")
            for size, contexts in m["search"].items():
                for context_name, queries in contexts.items():
                    out.append(f"    {size:>6} context={context_name}")
                    for query_name, modes in queries.items():
                        diag = modes["diagnostic"]
                        out.append(
                            f"      {query_name:<14} matches={diag['match_count']} "
                            f"index={diag['index_bytes']} bytes")
                        for mode in ("no_cache", "cold_cache", "warm_cache"):
                            q = modes[mode]
                            out.append(
                                f"        {mode:<10} {q['p50_ms']:>9.1f} / "
                                f"{q['p95_ms']:>9.1f} / {q['p99_ms']:>9.1f} "
                                f"(n={q['runs']}, rc={q['returncodes']})")
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
