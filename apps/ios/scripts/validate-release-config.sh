#!/bin/sh
set -eu
case "${HYMIO_BACKEND_URL:-}" in
  https://?*) ;;
  *) echo 'error: Set HYMIO_BACKEND_URL to your HTTPS backend in Config/Local.xcconfig before archiving.' >&2; exit 1 ;;
esac
case "$HYMIO_BACKEND_URL" in
  *invalid.example*|*hymio.example.com*)
    echo 'error: Release backend is a placeholder. Configure Config/Local.xcconfig before archiving.' >&2
    exit 1 ;;
esac
