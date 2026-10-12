#!/usr/bin/env bash

# Mirror an existing GitHub Release into the browser-facing client-data branch.
# This is intentionally safe to rerun: it preserves other tag directories and
# only commits when the selected tag or root manifest actually changes.
set -euo pipefail

TAG="${1:-}"
REPO="${2:-}"

if [[ ! "$TAG" =~ ^v[1-9][0-9]*$ ]]; then
  echo "Usage: $0 v1 [owner/repository]" >&2
  exit 1
fi

command -v gh >/dev/null || { echo "ERROR: GitHub CLI (gh) is required" >&2; exit 1; }
command -v git >/dev/null || { echo "ERROR: git is required" >&2; exit 1; }
command -v python >/dev/null || { echo "ERROR: python is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "ERROR: curl is required" >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "ERROR: sha256sum is required" >&2; exit 1; }

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"
fi

ROOT="$(git rev-parse --show-toplevel)"
TMP_DIR="$(mktemp -d)"
WORKTREE="$TMP_DIR/client-data"
WORKTREE_CREATED=0
cleanup() {
  if [[ "$WORKTREE_CREATED" == 1 ]]; then
    git -C "$ROOT" worktree remove --force "$WORKTREE" 2>/dev/null || true
  fi
  rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT

gh release download "$TAG" --repo "$REPO" --pattern 'manifest.json' --pattern '*.db.gz' --dir "$TMP_DIR/release"

python - "$TMP_DIR/release/manifest.json" "$TAG" "$REPO" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
tag = sys.argv[2]
repo = sys.argv[3]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest.get("releaseVersion") != int(tag[1:]):
    raise SystemExit("ERROR: releaseVersion does not match tag")
for pack in manifest.get("packs", []):
    filename = pack["file"]
    if not (manifest_path.parent / filename).is_file():
        raise SystemExit(f"ERROR: missing release asset {filename}")
PY

python - "$TMP_DIR/release/manifest.json" <<'PY'
import gzip
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
for pack in manifest["packs"]:
    path = manifest_path.parent / pack["file"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != pack["sha256"]:
        raise SystemExit(f"ERROR: checksum mismatch for {path.name}")
    with gzip.open(path, "rb") as handle:
        while handle.read(1024 * 1024):
            pass
PY

while IFS= read -r pack; do
  python "$ROOT/scripts/inspect_pack.py" "$TMP_DIR/release/$pack"
done < <(python - "$TMP_DIR/release/manifest.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    for pack in json.load(handle)["packs"]:
        print(pack["file"])
PY
)

set +e
git ls-remote --exit-code --heads origin client-data >/dev/null
CLIENT_DATA_REMOTE_STATUS=$?
set -e
case "$CLIENT_DATA_REMOTE_STATUS" in
  0) git -C "$ROOT" fetch origin \
       "+refs/heads/client-data:refs/remotes/origin/client-data" ;;
  2) ;;
  *) echo "ERROR: unable to query origin/client-data" >&2; exit "$CLIENT_DATA_REMOTE_STATUS" ;;
esac
if git -C "$ROOT" show-ref --verify --quiet refs/remotes/origin/client-data; then
  if git -C "$ROOT" show-ref --verify --quiet refs/heads/client-data; then
    if ! git -C "$ROOT" merge-base --is-ancestor client-data refs/remotes/origin/client-data; then
      echo "ERROR: local client-data branch is ahead of or diverges from origin/client-data" >&2
      exit 1
    fi
  else
    git -C "$ROOT" branch --track client-data refs/remotes/origin/client-data
  fi
  git -C "$ROOT" worktree add "$WORKTREE" client-data
  WORKTREE_CREATED=1
  git -C "$WORKTREE" merge --ff-only refs/remotes/origin/client-data
else
  if git -C "$ROOT" show-ref --verify --quiet refs/heads/client-data; then
    echo "ERROR: local client-data exists but origin/client-data does not; refusing to replace it" >&2
    exit 1
  fi
  git -C "$ROOT" worktree add --detach "$WORKTREE"
  WORKTREE_CREATED=1
  git -C "$WORKTREE" switch --orphan client-data
  git -C "$WORKTREE" rm -r --ignore-unmatch .
  git -C "$WORKTREE" clean -fdx
fi

python "$ROOT/scripts/client_mirror.py" "$TMP_DIR/release/manifest.json" \
  --repository "$REPO" --tag "$TAG" --allow-legacy-v1-urls \
  --publish-worktree "$WORKTREE" --assets-dir "$TMP_DIR/release"
git -C "$WORKTREE" add manifest.json "$TAG"
if git -C "$WORKTREE" diff --cached --quiet; then
  echo "client-data is already current for $TAG"
else
  git -C "$WORKTREE" config user.name "MetroPocket release tooling"
  git -C "$WORKTREE" config user.email "release-tooling@users.noreply.github.com"
  git -C "$WORKTREE" commit -m "Bootstrap browser data $TAG"
  git -C "$WORKTREE" push origin HEAD:client-data
fi

echo "==> Waiting for raw client-data mirror"
for attempt in {1..15}; do
  curl -fsSL "https://raw.githubusercontent.com/$REPO/client-data/manifest.json" \
    -o "$TMP_DIR/raw-manifest.json" || true
  if cmp -s "$WORKTREE/manifest.json" "$TMP_DIR/raw-manifest.json"; then
    MIRROR_OK=1
    while IFS= read -r asset; do
      curl -fsSL "https://raw.githubusercontent.com/$REPO/client-data/$TAG/$asset" \
        -o "$TMP_DIR/raw-$asset" || { MIRROR_OK=0; break; }
      [[ "$(sha256sum "$WORKTREE/$TAG/$asset" | awk '{print $1}')" == "$(sha256sum "$TMP_DIR/raw-$asset" | awk '{print $1}')" ]] || {
        MIRROR_OK=0; break;
      }
    done < <(find "$WORKTREE/$TAG" -maxdepth 1 -type f -name '*.db.gz' -printf '%f\n')
    [[ "${MIRROR_OK:-0}" == 1 ]] && break
  fi
  sleep 4
done
[[ "${MIRROR_OK:-0}" == 1 ]] || { echo "ERROR: raw client-data mirror did not converge" >&2; exit 1; }
