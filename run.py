#!/usr/bin/env python3
"""
Simple runner script for the Church Anniversary & Birthday Helper.
"""
import sys
import asyncio
import uvicorn
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app


def main():
    """Main entry point."""
    print("🎉 Starting Church Anniversary & Birthday Helper...")
    print("📖 Visit http://localhost:8000/docs for API documentation")
    print("❤️  Visit http://localhost:8000/health for health check")
    print("🛑 Press Ctrl+C to stop")

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Goodbye! God bless your ministry!")


if __name__ == "__main__":
    main()
