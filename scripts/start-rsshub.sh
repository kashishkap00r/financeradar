#!/bin/bash
# Start RSSHub server for FinanceRadar Twitter feeds
cd "$HOME/vibecoding projects/rsshub-test" || exit 1
source .env 2>/dev/null
export NODE_ENV=dev
export NODE_OPTIONS='--max-http-header-size=32768'
exec node node_modules/.bin/tsx lib/index.ts
