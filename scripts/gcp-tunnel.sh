#!/usr/bin/env bash
# =============================================================
#  DroidFarm  -  GCP localhost tunnel
#
#  Opens an SSH local-port-forward from your laptop to a DroidFarm
#  instance running on a GCE VM. The DroidFarm backend binds to
#  127.0.0.1 on the VM, so this tunnel is the only way to reach it
#  from outside the VM. No firewall rules required.
#
#  Usage:
#      ./scripts/gcp-tunnel.sh
#      INSTANCE_NAME=my-farm ZONE=us-east1-b ./scripts/gcp-tunnel.sh
#
#  Then open http://localhost:7870 in your browser.
#  Ctrl-C to disconnect.
# =============================================================
set -euo pipefail

INSTANCE_NAME="${INSTANCE_NAME:-droidfarm}"
ZONE="${ZONE:-us-central1-a}"
DROIDFARM_PORT="${DROIDFARM_PORT:-7870}"
LOCAL_PORT="${LOCAL_PORT:-$DROIDFARM_PORT}"

command -v gcloud >/dev/null 2>&1 \
  || { echo "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install" >&2; exit 1; }

cat <<EOF
[gcp-tunnel] forwarding localhost:$LOCAL_PORT  ->  $INSTANCE_NAME:$DROIDFARM_PORT (via IAP)
[gcp-tunnel] open http://localhost:$LOCAL_PORT in your browser. Ctrl-C to stop.
EOF

# -N: don't run a remote command, just keep the channel open.
# -L: local-forward; binds your laptop's $LOCAL_PORT to the VM's 127.0.0.1:$DROIDFARM_PORT.
# --tunnel-through-iap: works even when the VM has no public IP.
exec gcloud compute ssh "$INSTANCE_NAME" \
  --zone="$ZONE" \
  --tunnel-through-iap \
  -- \
  -N -L "${LOCAL_PORT}:127.0.0.1:${DROIDFARM_PORT}"
