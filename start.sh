#!/bin/bash
# Render startup script
gunicorn --bind 0.0.0.0:${PORT:-10000} app:app --timeout 120 --workers 2 --log-level info
