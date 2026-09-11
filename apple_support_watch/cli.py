from __future__ import annotations

import argparse
import json
from pathlib import Path

from .watcher import Watcher


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch Apple Support sitemaps and publish RSS feeds")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", default="config/sources.json")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--bootstrap-batch-size", type=int)
    run_parser.add_argument("--audit-batch-size", type=int)
    args = parser.parse_args(argv)

    root = Path.cwd()
    config_path = root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.bootstrap_batch_size is not None:
        config["bootstrap_batch_size"] = args.bootstrap_batch_size
    if args.audit_batch_size is not None:
        config["audit_batch_size"] = args.audit_batch_size
    status = Watcher(root, config, dry_run=args.dry_run).run()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0
