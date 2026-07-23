#!/bin/sh
# RAC write-cadence nudge (installed by `decided hook install`).
#
# Advisory only: after each commit it prints the write-cadence nudge when the
# corpus has gone quiet, and never blocks or fails the commit. Remove this file
# to stop the nudge.

if ! command -v decided >/dev/null 2>&1; then
	echo "decided: not on PATH; skipping write-cadence nudge" >&2
	exit 0
fi

dir="decisions"
[ -d "$dir" ] || dir="."

# Print only the cadence line; swallow everything else. Always succeed.
decided review "$dir" --stale-after 2>/dev/null | grep "No product knowledge recorded" || true
exit 0
