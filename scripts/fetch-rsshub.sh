#!/bin/bash
# Fetch Twitter via local RSSHub and push to GitHub
cd "$HOME/vibecoding projects/financeradar" || exit 1

# Wait for RSSHub to be ready
for i in $(seq 1 30); do
    curl -s -o /dev/null http://localhost:1200/healthz && break
    sleep 2
done

python3 rsshub_local_fetch.py --push
