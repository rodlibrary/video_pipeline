"""Run the AV pipeline locally from a terminal.

Examples:
    python run_pipeline.py --config config.yaml           # run workflow.steps from the config
    python run_pipeline.py --list                         # show steps and whether each is enabled
    python run_pipeline.py --steps transcribe keyframes   # run only these steps
    python run_pipeline.py --skip transcribe              # run everything except transcription
    python run_pipeline.py --check                        # only check prerequisites

Each step runs as its own Python process (the same interpreter that runs this
script), one after another. Relative paths in the config are resolved against
the folder that contains the config file, so you can run this from anywhere.

Cluster users can still fan steps out over MPI with ``--mpi --ranks N``
(requires ``mpi4py`` and an MPI installation).
"""

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import yaml

from pipeline_common import resolve_api_key, resolve_base_url

SCRIPT_ROOT = os.path.dirname(os.path.abspath(__file__))

# step name -> (script, config section holding `enabled`, short description)
PIPELINE_STEPS: Dict[str, Tuple[str, Optional[str], str]] = {
    "transcribe": ("transcribe_collection.py", None, "Whisper speech-to-text"),
    "keyframes": ("extract_keyframes.py", "keyframes", "Still frames via ffmpeg"),
    "describe_frames": ("describe_frames.py", "frame_descriptions", "Vision-model frame descriptions"),
    "summarize": ("summarize_collection.py", "summarization", "Per-item summaries"),
    "tags": ("generate_tags.py", "tagging", "Entity/topic tags (JSON)"),
    "accessibility": ("generate_accessibility.py", "accessibility", "Audio-description cues"),
    "collection_report": ("collection_report.py", "collection_reports", "Collection-wide briefing"),
    "preview": ("build_preview.py", "preview_dashboard", "Static HTML dashboard"),
    "quality_metrics": ("quality_metrics.py", "quality_control", "QA metrics CSV"),
    "iiif": ("build_iiif_manifest.py", "iiif", "IIIF manifest"),
    "catalog_export": ("export_catalog.py", "catalog_export", "Catalog CSV export"),
    "search_index": ("build_search_index.py", "search_index", "SQLite full-text index"),
    "clustering": ("cluster_visuals.py", "clustering", "Embedding + k-means clusters"),
}

# Kept for backwards compatibility with code that imported the old mapping.
PIPELINE_CMDS = {name: spec[0] for name, spec in PIPELINE_STEPS.items()}

AI_CHAT_STEPS = {"describe_frames", "summarize", "tags", "accessibility", "collection_report"}
AI_EMBED_STEPS = {"clustering"}

STEP_PYTHON_DEPS = {
    "transcribe": [("whisper", "openai-whisper")],
    "describe_frames": [("openai", "openai")],
    "summarize": [("openai", "openai")],
    "tags": [("openai", "openai")],
    "accessibility": [("openai", "openai")],
    "collection_report": [("openai", "openai")],
    "preview": [("jinja2", "jinja2")],
    "quality_metrics": [("pandas", "pandas")],
    "clustering": [("openai", "openai"), ("sklearn", "scikit-learn")],
}


def load_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Configuration file must define a mapping.")
    return config


def step_enabled(step: str, config: Dict) -> bool:
    section = PIPELINE_STEPS[step][1]
    if section is None:
        return True
    return bool(config.get(section, {}).get("enabled", False))


def color(text: str, code: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def resolve_steps(args: argparse.Namespace, config: Dict) -> List[str]:
    if args.steps:
        steps = list(args.steps)
    else:
        steps = list(config.get("workflow", {}).get("steps") or PIPELINE_STEPS.keys())

    unknown = [s for s in steps + (args.skip or []) if s not in PIPELINE_STEPS]
    if unknown:
        raise SystemExit(
            f"Unknown step(s): {', '.join(unknown)}. Valid steps: {', '.join(PIPELINE_STEPS)}",
        )
    skip = set(args.skip or [])
    return [s for s in steps if s not in skip]


def preflight(steps: List[str], config: Dict, config_dir: str) -> List[str]:
    """Return a list of human-readable problems that would make steps fail."""
    problems: List[str] = []

    needs_ffmpeg = "keyframes" in steps or (
        "transcribe" in steps and config.get("preprocessing", {}).get("extract_audio", False)
    )
    # Whisper itself shells out to ffmpeg to decode media, so transcription always needs it.
    if "transcribe" in steps:
        needs_ffmpeg = True
    if needs_ffmpeg and shutil.which("ffmpeg") is None:
        problems.append("ffmpeg is not on your PATH (install it: `brew install ffmpeg`, `apt install ffmpeg`, "
                        "or `winget install ffmpeg`).")
    if "keyframes" in steps and shutil.which("ffprobe") is None:
        problems.append("ffprobe is not on your PATH (it ships with ffmpeg).")

    missing_pkgs = set()
    for step in steps:
        for module, package in STEP_PYTHON_DEPS.get(step, []):
            if importlib.util.find_spec(module) is None:
                missing_pkgs.add(package)
    if missing_pkgs:
        problems.append(
            f"Missing Python package(s): {', '.join(sorted(missing_pkgs))}. "
            "Run `pip install -r requirements.txt`.",
        )

    if "transcribe" in steps or "keyframes" in steps:
        media_root = config.get("input", {}).get("media_root")
        if not media_root:
            problems.append("`input.media_root` is not set in the config.")
        else:
            path = os.path.abspath(os.path.join(config_dir, os.path.expanduser(media_root)))
            if not os.path.isdir(path):
                problems.append(f"Media folder does not exist: {path}")

    section_by_step = {s: PIPELINE_STEPS[s][1] for s in steps}
    for step in steps:
        if step not in AI_CHAT_STEPS | AI_EMBED_STEPS:
            continue
        section_cfg = config.get(section_by_step[step], {})
        if not resolve_api_key(section_cfg) and not resolve_base_url(section_cfg):
            env = section_cfg.get("api_key_env", "OPENAI_API_KEY")
            problems.append(
                f"Step '{step}' needs an API key: set {env} (e.g. `export {env}=...`), "
                f"or set `{section_by_step[step]}.base_url` to a local model server.",
            )

    # De-duplicate while keeping order (several steps can share one missing key).
    seen = set()
    unique = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def build_command(step: str, config_path: str, use_mpi: bool, ranks: int) -> List[str]:
    script_path = os.path.join(SCRIPT_ROOT, PIPELINE_STEPS[step][0])
    base = [sys.executable, "-u", script_path, "--config", config_path]
    if use_mpi:
        return ["mpirun", "-np", str(ranks)] + base
    return base


def run_step(step: str, command: List[str], cwd: str, env: Dict[str, str]) -> Tuple[int, float]:
    start = time.time()
    try:
        proc = subprocess.run(command, cwd=cwd, env=env)
        code = proc.returncode
    except KeyboardInterrupt:
        code = 130
    return code, time.time() - start


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def print_step_list(config: Dict, selected: List[str]) -> None:
    print(f"{'step':<18} {'enabled':<8} {'selected':<9} description")
    for name, (_, section, desc) in PIPELINE_STEPS.items():
        enabled = "yes" if step_enabled(name, config) else "no"
        chosen = "yes" if name in selected else ""
        where = f" [{section}.enabled]" if section else ""
        print(f"{name:<18} {enabled:<8} {chosen:<9} {desc}{where}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the AV pipeline locally, step by step, with provenance logging.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Steps: " + ", ".join(PIPELINE_STEPS),
    )
    parser.add_argument("--config", default="config.yaml", help="YAML config file (default: ./config.yaml).")
    parser.add_argument("--steps", nargs="+", metavar="STEP", help="Run only these steps, in this order.")
    parser.add_argument("--skip", nargs="+", metavar="STEP", help="Skip these steps.")
    parser.add_argument("--list", action="store_true", help="List steps and whether each is enabled, then exit.")
    parser.add_argument("--check", action="store_true", help="Check prerequisites for the selected steps, then exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands that would run, then exit.")
    parser.add_argument("--keep-going", action="store_true", help="Continue with later steps after a step fails.")
    parser.add_argument("--skip-checks", action="store_true", help="Run even if prerequisite checks fail.")
    parser.add_argument("--mpi", action="store_true", help="Launch each step with mpirun (cluster use; needs mpi4py).")
    parser.add_argument("--ranks", type=int, default=4, help="MPI ranks per step with --mpi (default: 4).")
    parser.add_argument("--no-mpi", action="store_true", help="Never use mpirun, even inside a SLURM job.")
    args = parser.parse_args()

    config_path = os.path.abspath(os.path.expanduser(args.config))
    if not os.path.isfile(config_path):
        example = os.path.join(SCRIPT_ROOT, "config-local.yaml")
        sys.exit(
            f"Config file not found: {config_path}\n"
            f"Start from the local template:  cp {example} config.yaml",
        )
    config_dir = os.path.dirname(config_path)
    try:
        config = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Could not read config {config_path}: {exc}")

    selected = resolve_steps(args, config)

    if args.list:
        print_step_list(config, selected)
        return

    runnable = [s for s in selected if step_enabled(s, config)]
    disabled = [s for s in selected if s not in runnable]
    if args.steps:
        # The user named these steps explicitly, so say exactly how to turn each one on.
        for step in disabled:
            section = PIPELINE_STEPS[step][1]
            print(color(f"[run_pipeline] Skipping '{step}': set `{section}.enabled: true` in the config to run it.",
                        "33"))
    elif disabled:
        print(color(f"[run_pipeline] Disabled in config (skipped): {', '.join(disabled)}. "
                    "See --list for how to enable them.", "33"))

    if not runnable:
        sys.exit("No enabled steps to run. Use --list to see which steps are enabled.")

    # Inside a SLURM job (e.g. the scripts in av_pipeline_slurm_chain.zip), keep the
    # original behaviour of launching steps with mpirun unless --no-mpi is given.
    if not args.mpi and not args.no_mpi and os.environ.get("SLURM_JOB_ID") and shutil.which("mpirun"):
        args.mpi = True
        print("[run_pipeline] SLURM job detected; launching steps with mpirun (pass --no-mpi to disable).")

    if args.mpi and shutil.which("mpirun") is None:
        sys.exit("--mpi was given but `mpirun` is not on your PATH.")

    problems = [] if args.skip_checks else preflight(runnable, config, config_dir)
    if problems:
        print(color("[run_pipeline] Prerequisite problems:", "31"), file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        if args.check or not args.dry_run:
            sys.exit("Fix the above, or pass --skip-checks to run anyway.")
    elif args.check:
        print(f"[run_pipeline] All prerequisites look good for: {', '.join(runnable)}")
        return

    commands = {s: build_command(s, config_path, args.mpi, args.ranks) for s in runnable}
    if args.dry_run:
        print(f"[run_pipeline] Working directory: {config_dir}")
        for step in runnable:
            print(" ".join(commands[step]))
        return

    env = dict(os.environ)
    # Make `import pipeline_common` work no matter where the user launches from.
    env["PYTHONPATH"] = SCRIPT_ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if not args.mpi:
        env["AV_PIPELINE_FORCE_SERIAL"] = "1"

    provenance_cfg = config.get("provenance", {})
    provenance_enabled = provenance_cfg.get("enabled", True)
    provenance_log = os.path.abspath(
        os.path.join(config_dir, os.path.expanduser(provenance_cfg.get("log_path", "provenance_log.jsonl"))),
    )
    record: Dict = {
        "config_path": config_path,
        "workflow_steps": runnable,
        "skipped_disabled": disabled,
        "mode": "mpi" if args.mpi else "local",
        "python": sys.executable,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
    }

    results: List[Tuple[str, int, float]] = []
    success = True
    total = len(runnable)
    for idx, step in enumerate(runnable, start=1):
        print(color(f"\n[run_pipeline] ({idx}/{total}) {step}: {PIPELINE_STEPS[step][2]}", "1;36"), flush=True)
        start_ts = datetime.now(timezone.utc).isoformat()
        code, duration = run_step(step, commands[step], config_dir, env)
        results.append((step, code, duration))
        record["steps"].append({
            "step": step,
            "command": commands[step],
            "start": start_ts,
            "duration_sec": round(duration, 3),
            "returncode": code,
        })
        if code in (130, -signal.SIGINT):
            print(color("[run_pipeline] Interrupted.", "31"), file=sys.stderr)
            success = False
            break
        if code != 0:
            success = False
            print(color(f"[run_pipeline] Step '{step}' failed (exit code {code}).", "31"), file=sys.stderr)
            if not args.keep_going:
                break

    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    record["success"] = success

    print(color("\n[run_pipeline] Summary", "1"))
    for step, code, duration in results:
        status = color("ok", "32") if code == 0 else color(f"failed ({code})", "31")
        print(f"  {step:<18} {status:<10} {format_duration(duration)}")
    not_run = [s for s in runnable if s not in {r[0] for r in results}]
    for step in not_run:
        print(f"  {step:<18} not run")

    if provenance_enabled:
        os.makedirs(os.path.dirname(provenance_log), exist_ok=True)
        with open(provenance_log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[run_pipeline] Provenance appended to {provenance_log}")

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
