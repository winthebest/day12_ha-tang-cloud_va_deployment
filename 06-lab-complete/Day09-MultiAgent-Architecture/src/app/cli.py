from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.graph import ShoppingAssistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shopping assistant multi-agent CLI.")
    parser.add_argument("--question", help="Run one question through the graph.")
    parser.add_argument("--test-file", default="data/test.json")
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--batch", action="store_true")
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force rebuild the Chroma policy index before running.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    assistant = ShoppingAssistant()

    if args.batch:
        test_file = Path(args.test_file)
        output_dir = (
            Path(args.trace_file)
            if args.trace_file
            else Path("src/artifacts/traces")
        )
        summary = assistant.run_batch(
            test_file=test_file,
            output_dir=output_dir,
            rebuild_index=args.rebuild_index,
        )
        print("\n=== Batch Summary ===")
        print(f"Total: {summary['total']}")
        print(f"Route accuracy:  {summary['route_accuracy']:.1%}")
        print(f"Status accuracy: {summary['status_accuracy']:.1%}")

    elif args.question:
        trace_file = Path(args.trace_file) if args.trace_file else None
        result = assistant.ask(
            args.question,
            trace_file=trace_file,
            rebuild_index=args.rebuild_index,
        )
        print("\n=== Final Answer ===")
        print(result.get("final_answer", "(no answer)"))
        if trace_file:
            print(f"\nTrace saved to: {trace_file}")

    else:
        print("Usage:")
        print("  Single question: --question 'Chính sách hoàn trả hàng ra sao?'")
        print("  Batch test:      --batch [--test-file data/test.json]")
        print("  Save trace:      --trace-file path/to/trace.json")


if __name__ == "__main__":
    main()
