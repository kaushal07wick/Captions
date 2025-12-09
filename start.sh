#!/bin/sh
set -e

echo "🚀 Starting CaptionGen FastAPI server..."

# Change to correct directory
cd /app/api

# Start FastAPI via Uvicorn
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
