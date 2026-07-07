#!/usr/bin/env python3
"""
Launch script for the FastAPI backend.

Usage:
    python run_backend.py              # Default: localhost:8000
    python run_backend.py --port 8080  # Custom port
    python run_backend.py --reload     # Dev mode with auto-reload
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="GDELT Analysis Platform Backend")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()
    
    print(f"🚀 Starting GDELT Analysis Platform")
    print(f"   Mode: {'development (reload)' if args.reload else 'production'}")
    print(f"   URL: http://{args.host}:{args.port}")
    print(f"   API Docs: http://{args.host}:{args.port}/docs")
    print(f"   Press Ctrl+C to stop\n")
    
    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info",
    )


if __name__ == "__main__":
    main()
