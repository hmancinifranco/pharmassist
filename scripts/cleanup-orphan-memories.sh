#!/usr/bin/env bash
# cleanup-orphan-memories.sh — Borra memorias de AgentCore que quedaron huérfanas
# después de 'agentcore destroy'. El CLI preserva memorias pre-existentes,
# pero en nuestro caso conviene borrarlas porque no se reusan.
#
# Uso:
#   bash scripts/cleanup-orphan-memories.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

[ -f "$ENV_FILE" ] || (echo "✗ $ENV_FILE no existe." && exit 1)

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"

python3 - <<PYEOF
import boto3
import os

profile = os.environ.get("AWS_PROFILE", "default")
region = os.environ.get("AWS_REGION", "us-east-1")

session = boto3.Session(profile_name=profile, region_name=region)
client = session.client("bedrock-agentcore-control")

try:
    response = client.list_memories()
    memories = response.get("memories", [])
except Exception as e:
    print(f"⚠ No se pudieron listar memorias: {e}")
    raise SystemExit(0)

if not memories:
    print("  ✓ No hay memorias huérfanas.")
    raise SystemExit(0)

# Borrar solo las que tienen nombre prefijado con agent_mem o pharmassist_*_mem
deleted = 0
for mem in memories:
    mem_id = mem.get("id") or mem.get("memoryId")
    mem_name = mem.get("name") or mem.get("memoryName") or ""
    if not mem_id:
        continue
    if mem_name.startswith("agent_mem") or mem_name.startswith("pharmassist_") or mem_name.startswith("bidivoice_"):
        try:
            client.delete_memory(memoryId=mem_id)
            print(f"  ✓ Borrada memoria: {mem_id} ({mem_name})")
            deleted += 1
        except Exception as e:
            print(f"  ⚠ No se pudo borrar {mem_id}: {e}")

if deleted == 0:
    print("  ✓ No hay memorias de PharmAssist para limpiar.")
else:
    print(f"  ✓ {deleted} memorias huérfanas eliminadas.")
PYEOF
