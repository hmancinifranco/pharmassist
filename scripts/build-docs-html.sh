#!/usr/bin/env bash
# ============================================================================
# Regenera los exportables HTML de docs/ desde su fuente Markdown.
#
# Los .html de docs/ están en .gitignore: son artefactos derivados que se
# comparten con stakeholders, no fuente de verdad. Este script existe para que
# no vuelvan a quedar desincronizados del Markdown.
#
# Uso:  bash scripts/build-docs-html.sh     (o: make docs-html)
# Requiere: pandoc (brew install pandoc)
# ============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$PROJECT_ROOT/docs"

if ! command -v pandoc >/dev/null 2>&1; then
  echo "✗ pandoc no está instalado. Instalalo con: brew install pandoc"
  exit 1
fi

# Cada entrada: "<md source>|<html output>|<template>|<title>"
DOCUMENTS=(
  "road-to-prod.md|road-to-prod.html|road-to-prod.template.html|De Demo a MLP Productivo"
)

for entry in "${DOCUMENTS[@]}"; do
  IFS='|' read -r src out tpl title <<<"$entry"

  if [ ! -f "$DOCS_DIR/$src" ]; then
    echo "✗ No existe $DOCS_DIR/$src — se omite."
    continue
  fi
  if [ ! -f "$DOCS_DIR/$tpl" ]; then
    echo "✗ No existe el template $DOCS_DIR/$tpl — se omite $src."
    continue
  fi

  echo "→ $src → $out"
  pandoc "$DOCS_DIR/$src" \
    --from gfm \
    --to html5 \
    --standalone \
    --toc \
    --toc-depth=2 \
    --template "$DOCS_DIR/$tpl" \
    --metadata title="$title" \
    --output "$DOCS_DIR/$out"
done

echo "✓ HTML regenerado en docs/."
echo "  Los bloques \`\`\`mermaid se renderizan en el browser vía mermaid.min.js."
