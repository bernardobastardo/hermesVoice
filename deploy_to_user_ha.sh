#!/usr/bin/env bash
set -euo pipefail

# Deploy the Hermes Agent Home Assistant custom component to the user's verified HA host.
# Host facts for this environment:
# - SSH target: root@192.168.25.5
# - SSH port: 22222
# - Home Assistant config root: /config

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPONENT_SRC="$ROOT_DIR/integrations/homeassistant/custom_components/hermes_agent_conversation"
HA_HOST="root@192.168.25.5"
HA_PORT="22222"
HA_CONFIG_ROOT="/config"
HA_COMPONENT_DIR="$HA_CONFIG_ROOT/custom_components/hermes_agent_conversation"
HA_BACKUP_DIR="$HA_CONFIG_ROOT/custom_components_backup"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -p "$HA_PORT")

if [[ ! -d "$COMPONENT_SRC" ]]; then
  echo "Component source not found: $COMPONENT_SRC" >&2
  exit 1
fi

run_remote() {
  ssh "${SSH_OPTS[@]}" "$HA_HOST" "$@"
}

echo "==> Remote git status"
run_remote "git -C '$HA_CONFIG_ROOT' status --short --branch | sed -n '1,120p'"

echo
if run_remote "test -d '$HA_COMPONENT_DIR'"; then
  echo "==> Backing up existing component"
  run_remote "mkdir -p '$HA_BACKUP_DIR'; ts=\$(date +%Y%m%d-%H%M%S); cp -r '$HA_COMPONENT_DIR' '$HA_BACKUP_DIR/hermes_agent_conversation.bak.'\"\$ts\"; echo 'backup=$HA_BACKUP_DIR/hermes_agent_conversation.bak.'\"\$ts\""
else
  echo "==> No existing remote component to back up"
fi

echo
echo "==> Removing remote component directory before copy"
run_remote "rm -rf '$HA_COMPONENT_DIR'"

echo
SCPLINE=(scp -P "$HA_PORT" -r "$COMPONENT_SRC" "$HA_HOST:$HA_CONFIG_ROOT/custom_components/")
echo "==> Copying component"
"${SCPLINE[@]}"

echo
echo "==> Validating Home Assistant config"
run_remote "ha core check"

echo
echo "==> Restarting Home Assistant core"
run_remote "ha core restart"

echo
echo "==> Done"
