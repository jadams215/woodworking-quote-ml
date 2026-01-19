#!/usr/bin/env python
"""
Convenience script to run the Woodworking Quote Engine.

Usage:
    python run.py                  # Start the API server
    python run.py --train          # Train the ML model
    python run.py --prepare-data   # Prepare training data
    python run.py --validate       # Validate the should-cost model
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Woodworking Quote Engine")
    parser.add_argument(
        '--train',
        action='store_true',
        help='Train the ML adjustment model'
    )
    parser.add_argument(
        '--prepare-data',
        action='store_true',
        help='Prepare training data from source files'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate the should-cost model'
    )
    parser.add_argument(
        '--ingest',
        action='store_true',
        help='Ingest profitability data from Excel/text files'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port for the API server (default: 8000)'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host for the API server (default: 0.0.0.0)'
    )

    args = parser.parse_args()

    project_root = Path(__file__).parent

    if args.ingest:
        print("Ingesting profitability data...")
        subprocess.run([
            sys.executable, '-m', 'src.data.ingest_profitability'
        ], cwd=project_root)

    elif args.prepare_data:
        print("Preparing training data...")
        subprocess.run([
            sys.executable, '-m', 'src.data.prepare_data'
        ], cwd=project_root)

    elif args.validate:
        print("Validating should-cost model...")
        subprocess.run([
            sys.executable, '-m', 'src.models.validate_should_cost'
        ], cwd=project_root)

    elif args.train:
        print("Training ML model...")
        subprocess.run([
            sys.executable, '-m', 'src.models.ml_adjuster'
        ], cwd=project_root)

    else:
        # Start the API server
        print(f"Starting Quote Engine API on http://{args.host}:{args.port}")
        print(f"Web UI: http://localhost:{args.port}")
        print(f"API Docs: http://localhost:{args.port}/docs")
        print("\nPress Ctrl+C to stop\n")

        subprocess.run([
            sys.executable, '-m', 'uvicorn',
            'src.api.main:app',
            '--host', args.host,
            '--port', str(args.port),
            '--reload'
        ], cwd=project_root)


if __name__ == '__main__':
    main()
