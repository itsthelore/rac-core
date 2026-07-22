#!/bin/sh
# RAC artifact validation (installed by `decided hook install --style pre-commit`).
#
# Blocking: refuses the commit when a staged Markdown artifact fails
# `decided validate`. Remove this file to stop the check.

if ! command -v decided >/dev/null 2>&1; then
	echo "decided: not on PATH; skipping artifact validation" >&2
	exit 0
fi

staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.md')
[ -z "$staged" ] && exit 0

status=0
for f in $staged; do
	[ -f "$f" ] || continue
	if ! decided validate "$f" >/dev/null 2>&1; then
		echo "decided: validation failed for $f (run: decided validate $f)" >&2
		status=1
	fi
done
exit $status
