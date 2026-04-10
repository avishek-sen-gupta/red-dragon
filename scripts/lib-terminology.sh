#!/bin/bash
# Shared library for terminology scanning (pre-commit + history scan).
# Source this file; do not execute directly.

BLOCKLIST="$HOME/.config/git/blocklist.txt"
EXCLUDELIST="$HOME/.config/git/blocklist-exclude.txt"

# ── Colors ──────────────────────────────────────────────────────

RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
DIM="\033[2m"
BOLD="\033[1m"
RESET="\033[0m"

# ── Blocklist loading ──────────────────────────────────────────

load_pattern() {
  if [ ! -f "$BLOCKLIST" ]; then
    echo "No blocklist found at $BLOCKLIST"
    return 1
  fi
  PATTERN=$(grep -v '^\s*#' "$BLOCKLIST" | grep -v '^\s*$' | paste -sd '|' -)
  if [ -z "$PATTERN" ]; then
    echo "Blocklist is empty."
    return 1
  fi
  return 0
}

load_excludes() {
  EXCLUDE_ARGS=""
  if [ -f "$EXCLUDELIST" ]; then
    while IFS= read -r line; do
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line// }" ]] && continue
      EXCLUDE_ARGS="$EXCLUDE_ARGS -- ':!$line'"
    done < "$EXCLUDELIST"
  fi
}

# ── Formatting ─────────────────────────────────────────────────

snippet_around() {
  # Extract ~30 chars before and after the term, highlight the term in red
  local line="$1" term="$2"
  local raw
  raw=$(echo "$line" | awk -v t="$term" '{
    i = index($0, t)
    if (i > 0) {
      s = (i > 31) ? i - 30 : 1
      print substr($0, s, 60 + length(t))
    }
  }')
  # Highlight the matched term in the snippet
  echo "$raw" | sed "s/$term/$(printf "${RED}${term}${RESET}")/g"
}

print_table_header() {
  local title="$1"
  echo ""
  echo -e "${RED}${BOLD} $title ${RESET}"
  echo -e "${DIM}$(printf '%.0s─' {1..90})${RESET}"
  printf "  ${BOLD}%-14s %-30s %-10s %s${RESET}\n" "COMMIT" "LOCATION" "TERM" "CONTEXT"
  echo -e "${DIM}$(printf '%.0s─' {1..90})${RESET}"
}

print_table_row() {
  local sha="$1" location="$2" term="$3" context="$4"
  printf "  ${CYAN}%-14s${RESET} %-30s ${YELLOW}%-10s${RESET} ${DIM}...${RESET}%b${DIM}...${RESET}\n" \
    "$sha" "$location" "\"$term\"" "$context"
}

print_table_footer() {
  local count="$1"
  echo -e "${DIM}$(printf '%.0s─' {1..90})${RESET}"
  echo -e "  ${BOLD}$count hit(s)${RESET}"
  echo ""
}

print_clean() {
  echo ""
  echo -e "  ${GREEN}${BOLD}No forbidden terms found.${RESET}"
  echo ""
}

print_blocked() {
  echo -e "  ${RED}Blocklist:${RESET} $BLOCKLIST"
  echo -e "  Fix the content or update the blocklist to proceed."
  echo ""
}
