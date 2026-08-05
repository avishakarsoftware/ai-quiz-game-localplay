#!/usr/bin/env bash
#
# One-time GCP monitoring setup for the games backend (REVIEW-2026-08 O2).
#
# Creates, in the current gcloud project:
#   1. An email notification channel
#   2. A firewall rule admitting Google's uptime-check probes on 443
#      (REQUIRED here: the VM firewall restricts HTTPS to the home IP, so without
#      this rule every probe is silently dropped and the check reports DOWN forever)
#   3. An HTTPS uptime check on gamesapi.revelryapp.me/health (60s interval)
#   4. An alert policy: email when the uptime check fails
#
# REVIEW BEFORE RUNNING — this mutates project infra. Then:
#   ./scripts/setup-monitoring.sh you@example.com
#
# Idempotency: each step checks for an existing resource by display name and skips it,
# so re-running after a partial failure is safe.
#
# Cost: uptime checks + alerting at this volume are inside GCP's free tier.

set -euo pipefail

EMAIL="${1:-}"
if [[ -z "$EMAIL" ]]; then
    echo "Usage: $0 <alert-email>" >&2
    exit 1
fi

HOST="gamesapi.revelryapp.me"
CHECK_NAME="games-backend-health"
CHANNEL_NAME="games-backend-alerts"
POLICY_NAME="games-backend-down"
FIREWALL_RULE="allow-gcp-uptime-checks"

PROJECT=$(gcloud config get-value project 2>/dev/null)
echo "[monitoring] project: $PROJECT"

# --- 1. Notification channel -------------------------------------------------
CHANNEL=$(gcloud beta monitoring channels list \
    --filter="displayName='$CHANNEL_NAME'" --format="value(name)" 2>/dev/null | head -1)
if [[ -z "$CHANNEL" ]]; then
    echo "[monitoring] creating email channel -> $EMAIL"
    CHANNEL=$(gcloud beta monitoring channels create \
        --display-name="$CHANNEL_NAME" \
        --type=email \
        --channel-labels="email_address=$EMAIL" \
        --format="value(name)")
else
    echo "[monitoring] channel exists: $CHANNEL"
fi

# --- 2. Firewall: admit Google's uptime probes --------------------------------
# The probe source ranges are published by the Monitoring API. Without this rule the
# home-IP-only firewall drops every probe and the check flatlines as DOWN.
if gcloud compute firewall-rules describe "$FIREWALL_RULE" >/dev/null 2>&1; then
    echo "[monitoring] firewall rule exists: $FIREWALL_RULE"
else
    echo "[monitoring] fetching uptime-check source ranges..."
    TOKEN=$(gcloud auth print-access-token)
    RANGES=$(curl -sf -H "Authorization: Bearer $TOKEN" \
        "https://monitoring.googleapis.com/v3/uptimeCheckIps" \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(','.join(ip['ipAddress'] for ip in d.get('uptimeCheckIps', [])))")
    if [[ -z "$RANGES" ]]; then
        echo "[monitoring] ERROR: could not fetch probe IPs; firewall rule not created" >&2
        exit 1
    fi
    echo "[monitoring] creating firewall rule for $(echo "$RANGES" | tr ',' '\n' | wc -l | tr -d ' ') probe addresses"
    gcloud compute firewall-rules create "$FIREWALL_RULE" \
        --direction=INGRESS --action=ALLOW --rules=tcp:443 \
        --source-ranges="$RANGES" \
        --description="Google Cloud Monitoring uptime-check probes (setup-monitoring.sh). Probe IPs change rarely; re-create this rule if checks start flatlining."
fi

# --- 3. Uptime check ----------------------------------------------------------
EXISTING_CHECK=$(gcloud monitoring uptime list-configs \
    --filter="displayName='$CHECK_NAME'" --format="value(name)" 2>/dev/null | head -1)
if [[ -z "$EXISTING_CHECK" ]]; then
    echo "[monitoring] creating uptime check on https://$HOST/health"
    gcloud monitoring uptime create "$CHECK_NAME" \
        --resource-type=uptime-url \
        --resource-labels="host=$HOST,project_id=$PROJECT" \
        --protocol=https --port=443 --path=/health \
        --period=1 --timeout=10
else
    echo "[monitoring] uptime check exists: $EXISTING_CHECK"
fi

# --- 4. Alert policy ----------------------------------------------------------
EXISTING_POLICY=$(gcloud alpha monitoring policies list \
    --filter="displayName='$POLICY_NAME'" --format="value(name)" 2>/dev/null | head -1)
if [[ -n "$EXISTING_POLICY" ]]; then
    echo "[monitoring] alert policy exists: $EXISTING_POLICY"
else
    echo "[monitoring] creating alert policy"
    POLICY_JSON=$(mktemp)
    cat > "$POLICY_JSON" <<EOF
{
  "displayName": "$POLICY_NAME",
  "combiner": "OR",
  "conditions": [{
    "displayName": "uptime check failing",
    "conditionThreshold": {
      "filter": "metric.type=\\"monitoring.googleapis.com/uptime_check/check_passed\\" AND resource.type=\\"uptime_url\\" AND resource.labels.host=\\"$HOST\\"",
      "aggregations": [{
        "alignmentPeriod": "300s",
        "perSeriesAligner": "ALIGN_FRACTION_TRUE",
        "crossSeriesReducer": "REDUCE_MEAN",
        "groupByFields": ["resource.labels.host"]
      }],
      "comparison": "COMPARISON_LT",
      "thresholdValue": 0.5,
      "duration": "300s",
      "trigger": {"count": 1}
    }
  }],
  "notificationChannels": ["$CHANNEL"],
  "documentation": {
    "content": "gamesapi.revelryapp.me/health is failing. Check: gcloud compute ssh revelry-backend --zone us-central1-a --command 'docker ps; docker logs games-backend --tail 40'. A failed deploy auto-rolls-back (deploy-gcp.sh step 7); if this fired anyway, the VM or nginx is the likely culprit."
  }
}
EOF
    gcloud alpha monitoring policies create --policy-from-file="$POLICY_JSON"
    rm -f "$POLICY_JSON"
fi

echo ""
echo "[monitoring] done. Verify at: https://console.cloud.google.com/monitoring/uptime?project=$PROJECT"
echo "[monitoring] NOTE: the email channel may require clicking a verification link sent to $EMAIL."
