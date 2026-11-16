#!/usr/bin/env bash
# Fails unless a version tag (v1.0.0, or v1.0.0-rc1 for a prerelease) matches the app's version in
# app/__init__.py and pyproject.toml. A release built from a mismatched tag would be named after the
# tag while the app, its games and PGN say another version. Used by desktop.yml and image.yml.
# Usage: scripts/tag_matches_version.sh v1.0.0
set -euo pipefail

app=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' app/__init__.py)
project=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)
tag=${1#v}
tag=${tag%%-*}
if [[ "$app" != "$tag" || "$project" != "$tag" ]]; then
  echo "Tag $1, app/__init__.py $app, pyproject.toml $project: they must match" >&2
  exit 1
fi
