#!/bin/sh
# RAC artifact validation (installed by `rac hook install --style pre-commit`).
#
# Blocking: refuses the commit when a staged Markdown artifact fails
# `rac validate`. Remove this file to stop the check.

if ! command -v rac >/dev/null 2>&1; then
	echo "rac: not on PATH; skipping artifact validation" >&2
	exit 0
fi

staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.md')
[ -z "$staged" ] && exit 0

status=0
for f in $staged; do
	[ -f "$f" ] || continue
	if ! rac validate "$f" >/dev/null 2>&1; then
		echo "rac: validation failed for $f (run: rac validate $f)" >&2
		status=1
	fi
done
exit $status
