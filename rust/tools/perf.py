#!/usr/bin/env python3
"""RAC engine performance harness (stdlib only).

Measures, per configured engine, over repeated runs:
  (a) engine startup            — `<bin> --version`
  (b) single-file validate      — validate one artifact
  (c) fresh corpus walk         — validate <dir> (flag-set per engine)
  (d) cold-walk throughput      — files/s at each corpus size present
  (e) peak RSS                  — /usr/bin/time -v, getrusage fallback

Reports median/min of >=7 runs (>=3 for the 20k size). Writes plain-text and
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


def _scratch_env(scratch):
    """Env that neutralizes the oracle usage ping / consent writes."""
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = os.path.join(scratch, "state")
    env["XDG_CONFIG_HOME"] = os.path.join(scratch, "config")
    env["XDG_CACHE_HOME"] = os.path.join(scratch, "cache")
    for k in list(env):
        if k in ("RAC_TIMING",):
            del env[k]
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


def _measure(bin_path, args, env, runs):
    times = []
    codes = set()
    for _ in range(runs):
        dt, rc = _time_run(bin_path, args, env)
        times.append(dt)
        codes.add(rc)
    return {
        "runs": runs,
        "median_ms": round(statistics.median(times), 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "returncodes": sorted(codes),
        "raw_ms": [round(t, 3) for t in times],
    }


def _peak_rss_kib(bin_path, args, env):
    """Peak RSS (KiB) for one run. Prefer /usr/bin/time -v, else getrusage."""
    time_bin = shutil.which("time") or (
        "/usr/bin/time" if os.path.exists("/usr/bin/time") else None)
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
    return max(after, before), "getrusage-children"


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

    def runs_for(size):
        if args.runs:
            return args.runs
        return int(runs_cfg.get(str(size), runs_cfg.get("default", 7)))

    # Resolve corpus dirs (relative to repo/tools) and existence + counts.
    present = {}
    for size, path in corpora.items():
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
        bin_path = ecfg["bin"]
        if not (os.path.isabs(bin_path) and os.path.exists(bin_path)):
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
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
