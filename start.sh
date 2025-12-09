#!/bin/sh
# 🚀 Start script for Railway (FastAPI)

echo "Starting CaptionGen FastAPI server..."
uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8000}
