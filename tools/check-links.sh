#!/usr/bin/env bash
#
# Enforces the one structural rule of this repository:
#
#   A document may only link to a LOWER-numbered document.
#
# That makes the reference graph a strict DAG — every edge decreases the number, so no path can return to
# where it started. No cycle detection is needed, and none is done here: the ordering IS the proof.
#
# Why it matters enough to have a script: a cycle between documents is not merely untidy. It means a
# concept has two homes, which means the two will disagree eventually, which means a reader — human or
# agent — is handed conflicting instructions with no way to tell which is current.
#
# README.md is the index. It may link anywhere, and nothing links to it.
#
# Exit 0 = the rule holds. Exit 1 = it does not, and every violation is printed.

set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
checked=0

# Markdown links to local .md files: [text](target.md) or [text](target.md#anchor)
link_targets() { grep -oE '\]\([^)]+\.md(#[^)]*)?\)' "$1" | sed -E 's/^\]\(//; s/\)$//; s/#.*$//'; }

# Leading number of a filename, or empty when it has none.
num_of() { echo "$1" | grep -oE '^[0-9]+' || true; }

for doc in *.md; do
  [ -e "$doc" ] || continue
  src_num=$(num_of "$doc")

  while read -r target; do
    [ -z "$target" ] && continue
    checked=$((checked + 1))

    # 1. the target must exist
    if [ ! -f "$target" ]; then
      echo "BROKEN   $doc -> $target   (no such file)"
      fail=1
      continue
    fi

    # 2. README is the index and is exempt from the ordering rule
    [ "$doc" = "README.md" ] && continue

    dst_num=$(num_of "$target")
    if [ -z "$src_num" ] || [ -z "$dst_num" ]; then
      echo "UNNUMBERED  $doc -> $target   (both ends must be numbered, or the rule cannot be checked)"
      fail=1
      continue
    fi

    # 3. the ordering rule itself
    if [ "$dst_num" -ge "$src_num" ]; then
      if [ "$dst_num" -eq "$src_num" ]; then
        echo "SELF/PEER  $doc -> $target   (equal number: a peer link can become a cycle)"
      else
        echo "UPWARD     $doc -> $target   ($dst_num >= $src_num: this is how a cycle starts)"
      fi
      fail=1
    fi
  done < <(link_targets "$doc")
done

# Nothing may link to README: it is the root of the graph, not a node in it.
if grep -lE '\]\(README\.md' -- *.md 2>/dev/null | grep -v '^README.md$' | grep -q .; then
  echo "INBOUND    something links to README.md, which is the index and must have no inbound edges:"
  grep -nE '\]\(README\.md' -- *.md 2>/dev/null | grep -v '^README.md:' | sed 's/^/           /'
  fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "OK  $checked internal links checked; every one points to a lower-numbered document."
else
  echo "FAILED — see above. Move the shared fact DOWN into the lower-numbered document and link to it,"
  echo "rather than linking upward or sideways."
fi
exit "$fail"
