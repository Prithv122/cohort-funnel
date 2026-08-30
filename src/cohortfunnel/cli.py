"""Console entry point: build, retention, funnel, compare."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import cohorts, funnels, warehouse
from .events import FUNNEL_STEPS


def _stdout_utf8() -> None:
    """Windows consoles still default to a legacy code page that cannot encode U+2192."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _print(frame: pd.DataFrame) -> None:
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(frame.to_string(index=False, na_rep="-"))


def _filters(args: argparse.Namespace) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    if args.channel:
        filters["channel"] = args.channel
    if args.platform:
        filters["platform"] = args.platform
    return filters


def cmd_build(args: argparse.Namespace) -> int:
    rows = warehouse.build(Path(args.database), seed=args.seed)
    print(f"Built {args.database} (seed {args.seed}): {rows:,} events")
    return 0


def cmd_retention(args: argparse.Namespace) -> int:
    with warehouse.connect(Path(args.database)) as con:
        long = cohorts.retention(
            con,
            period=args.period,
            activity_event=args.activity_event,
            max_periods=args.max_periods,
            filters=_filters(args),
        )
    matrix = cohorts.as_matrix(long).round(3)
    matrix.index = [str(value)[:10] for value in matrix.index]
    print(
        f"Retention on '{args.activity_event}', by {args.period} cohort. Blank = not yet observed."
    )
    _print(matrix.reset_index(names="cohort"))
    print()
    print("Blended curve (size-weighted, observed cells only):")
    curve = cohorts.blended_curve(long)
    curve["retention"] = curve["retention"].round(3)
    _print(curve)
    return 0


def cmd_funnel(args: argparse.Namespace) -> int:
    with warehouse.connect(Path(args.database)) as con:
        frame = funnels.funnel(
            con,
            args.steps,
            window_hours=args.window_hours,
            window_from=args.window_from,
            filters=_filters(args),
        )
    for column in ("step_conversion", "overall_conversion"):
        frame[column] = frame[column].round(4)
    frame["median_hours"] = frame["median_hours"].round(2)
    print(f"Window: {args.window_hours}h from {args.window_from}")
    _print(frame)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    with warehouse.connect(Path(args.database)) as con:
        frame = funnels.compare(
            con,
            args.steps,
            window_hours=args.window_hours,
            window_from=args.window_from,
            filters=_filters(args),
        )
    for column in ("overall_conversion_ordered", "overall_conversion_naive"):
        frame[column] = frame[column].round(4)
    print(f"Step-ordered ({args.window_hours}h from {args.window_from}) vs naive ever-fired:")
    _print(frame)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cohort-funnel", description=__doc__)
    parser.add_argument(
        "--database", default=str(warehouse.DEFAULT_DB), help="Path to the DuckDB warehouse"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_filters(p: argparse.ArgumentParser) -> None:
        p.add_argument("--channel", action="append", help="Filter to a channel (repeatable)")
        p.add_argument("--platform", action="append", help="Filter to a platform (repeatable)")

    def add_funnel_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--steps", nargs="+", default=list(FUNNEL_STEPS), help="Event names, in order"
        )
        p.add_argument("--window-hours", type=float, default=funnels.DEFAULT_WINDOW_HOURS)
        p.add_argument("--window-from", choices=funnels.WINDOW_ANCHORS, default="entry")
        add_filters(p)

    p_build = sub.add_parser("build", help="Generate the synthetic warehouse")
    p_build.add_argument("--seed", type=int, default=None)
    p_build.set_defaults(func=cmd_build)

    p_ret = sub.add_parser("retention", help="Cohort retention triangle")
    p_ret.add_argument("--period", choices=cohorts.PERIODS, default="week")
    p_ret.add_argument("--activity-event", default="lesson_start")
    p_ret.add_argument("--max-periods", type=int, default=8)
    add_filters(p_ret)
    p_ret.set_defaults(func=cmd_retention)

    p_fun = sub.add_parser("funnel", help="Step-ordered, windowed funnel")
    add_funnel_args(p_fun)
    p_fun.set_defaults(func=cmd_funnel)

    p_cmp = sub.add_parser("compare", help="Ordered funnel vs naive ever-fired counts")
    add_funnel_args(p_cmp)
    p_cmp.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    args = build_parser().parse_args(argv)
    if getattr(args, "seed", None) is None and args.command == "build":
        from .events import SEED

        args.seed = SEED
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
