#!/usr/bin/env bash

set -euo pipefail

TAG="${1:-}"
MODE="${2:-publish}"

WORKFLOW="release.yml"
BRANCH="master"

if [[ -z "$TAG" ]]; then
  echo "Usage:"
  echo "  $0 v2"
  echo "  $0 v1 --verify-only"
  exit 1
fi

if [[ ! "$TAG" =~ ^v([0-9]+)$ ]]; then
  echo "ERROR: tag must look like v1, v2, v3, ..."
  exit 1
fi

TAG_VERSION="${BASH_REMATCH[1]}"

command -v git >/dev/null || {
  echo "ERROR: git is required"
  exit 1
}

command -v gh >/dev/null || {
  echo "ERROR: GitHub CLI (gh) is required"
  exit 1
}

command -v python >/dev/null || {
  echo "ERROR: python is required"
  exit 1
}

command -v curl >/dev/null || {
  echo "ERROR: curl is required"
  exit 1
}

command -v gzip >/dev/null || {
  echo "ERROR: gzip is required"
  exit 1
}

command -v sha256sum >/dev/null || {
  echo "ERROR: sha256sum is required"
  exit 1
}

REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"

echo "Repository : $REPO"
echo "Tag        : $TAG"
echo "Mode       : $MODE"
echo

verify_release() {
  local verify_tag="$1"
  local tmp_dir

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT

  echo "==> Checking GitHub release"

  gh release view "$verify_tag" \
    --repo "$REPO" \
    --json tagName,name,assets,url \
    --jq '{
      tag: .tagName,
      name: .name,
      assets: [.assets[].name],
      url: .url
    }'

  echo
  echo "==> Downloading release manifest"

  gh release download "$verify_tag" \
    --repo "$REPO" \
    --pattern 'manifest.json' \
    --dir "$tmp_dir" \
    --clobber

  MANIFEST="$tmp_dir/manifest.json"

  python -m json.tool "$MANIFEST" >/dev/null

  RELEASE_VERSION="$(
    python - "$MANIFEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    manifest = json.load(f)

print(manifest["releaseVersion"])
PY
  )"

  if [[ "$RELEASE_VERSION" != "$TAG_VERSION" ]]; then
    echo "ERROR: manifest releaseVersion=$RELEASE_VERSION but tag=$verify_tag"
    exit 1
  fi

  echo "✓ Manifest JSON valid"
  echo "✓ releaseVersion=$RELEASE_VERSION"

  echo
  echo "==> Verifying all data packs"

  while IFS=$'\t' read -r FILE SHA URL; do
    [[ -z "$FILE" ]] && continue

    OUTPUT="$tmp_dir/$FILE"

    echo
    echo "Pack: $FILE"
    echo "URL : $URL"

    curl -4 -fL \
      --connect-timeout 15 \
      --max-time 120 \
      "$URL" \
      -o "$OUTPUT"

    gzip -t "$OUTPUT"

    ACTUAL_SHA="$(sha256sum "$OUTPUT" | awk '{print $1}')"

    if [[ "$ACTUAL_SHA" != "$SHA" ]]; then
      echo "ERROR: checksum mismatch for $FILE"
      echo "Expected: $SHA"
      echo "Actual:   $ACTUAL_SHA"
      exit 1
    fi

    echo "✓ gzip valid"
    echo "✓ checksum verified"

    if [[ -f scripts/inspect_pack.py ]]; then
      python scripts/inspect_pack.py "$OUTPUT"
    fi
  done < <(
    python - "$MANIFEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    manifest = json.load(f)

for pack in manifest["packs"]:
    print(
        pack["file"],
        pack["sha256"],
        pack["downloadUrl"],
        sep="\t",
    )
PY
  )

  LATEST_TAG="$(
    gh release view \
      --repo "$REPO" \
      --json tagName \
      --jq '.tagName'
  )"

  if [[ "$LATEST_TAG" == "$verify_tag" ]]; then
    echo
    echo "==> Verifying releases/latest manifest endpoint"

    LATEST_MANIFEST="$tmp_dir/latest-manifest.json"

    curl -4 -fsSL \
      --connect-timeout 15 \
      --max-time 60 \
      "https://github.com/$REPO/releases/latest/download/manifest.json" \
      -o "$LATEST_MANIFEST"

    python -m json.tool "$LATEST_MANIFEST" >/dev/null

    if ! cmp -s "$MANIFEST" "$LATEST_MANIFEST"; then
      echo "ERROR: latest manifest differs from $verify_tag manifest"
      exit 1
    fi

    echo "✓ latest manifest endpoint works"
    echo "✓ latest manifest matches $verify_tag"
  fi

  echo
  echo "========================================"
  echo "✓ Release $verify_tag verified successfully"
  echo "========================================"
}

if [[ "$MODE" == "--verify-only" ]]; then
  verify_release "$TAG"
  exit 0
fi

if [[ "$MODE" != "publish" ]]; then
  echo "ERROR: unknown mode: $MODE"
  exit 1
fi

echo "==> Checking GitHub authentication"
gh auth status >/dev/null

CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  echo "ERROR: releases must be published from '$BRANCH'"
  echo "Current branch: $CURRENT_BRANCH"
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is not clean"
  git status --short
  exit 1
fi

echo "==> Updating $BRANCH"
git pull --ff-only origin "$BRANCH"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree changed after pull"
  exit 1
fi

echo
echo "==> Checking releaseVersion"

CONFIG_VERSION="$(
  python - <<'PY'
import json

with open("release.json", encoding="utf-8") as f:
    print(json.load(f)["releaseVersion"])
PY
)"

if [[ "$CONFIG_VERSION" != "$TAG_VERSION" ]]; then
  echo "ERROR: release.json has releaseVersion=$CONFIG_VERSION"
  echo "       but requested tag is $TAG"
  echo
  echo "Update release.json before publishing."
  exit 1
fi

echo "✓ releaseVersion=$CONFIG_VERSION"

echo
echo "==> Checking whether $TAG already exists"

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "ERROR: GitHub release $TAG already exists"
  exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "ERROR: Git tag $TAG already exists on origin"
  exit 1
fi

echo "✓ $TAG is available"

echo
echo "==> Running local unit tests"
python -m unittest discover -s tests -v

echo
echo "==> Validating production sources"
python scripts/validate_sources.py

echo
echo "==> Checking whitespace"
git diff --check

echo
echo "==> Local release checks passed"

HEAD_SHA="$(git rev-parse HEAD)"

echo
echo "==> Triggering GitHub release workflow"

gh workflow run "$WORKFLOW" \
  --repo "$REPO" \
  --ref "$BRANCH" \
  -f tag="$TAG"

echo
echo "==> Waiting for workflow run"

RUN_ID=""

for _ in {1..20}; do
  RUN_ID="$(
    gh run list \
      --repo "$REPO" \
      --workflow "$WORKFLOW" \
      --branch "$BRANCH" \
      --event workflow_dispatch \
      --commit "$HEAD_SHA" \
      --limit 1 \
      --json databaseId \
      --jq '.[0].databaseId // empty'
  )"

  if [[ -n "$RUN_ID" ]]; then
    break
  fi

  sleep 2
done

if [[ -z "$RUN_ID" ]]; then
  echo "ERROR: unable to find triggered workflow run"
  exit 1
fi

echo "Workflow run: $RUN_ID"

gh run watch "$RUN_ID" \
  --repo "$REPO" \
  --exit-status

echo
echo "==> Workflow succeeded"

verify_release "$TAG"
