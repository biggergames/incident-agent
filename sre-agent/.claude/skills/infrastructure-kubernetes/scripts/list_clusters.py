#!/usr/bin/env python3
"""List K8s clusters registered for the current team.

Shows cluster ID, name, connection status, and metadata.
Use the cluster_id with --cluster-id on other scripts to route
commands through the k8s-gateway to remote clusters.

Usage:
    python list_clusters.py
    python list_clusters.py --json
"""

import argparse
import json
import os
import sys

import httpx


def get_config_service_headers() -> dict[str, str]:
    """Get auth headers for config-service requests."""
    headers: dict[str, str] = {}

    team_token = os.environ.get("TEAM_TOKEN")
    if team_token:
        headers["Authorization"] = f"Bearer {team_token}"
        return headers

    # Fallback: header-based auth
    tenant_id = os.environ.get("INCIDENTFOX_TENANT_ID")
    team_id = os.environ.get("INCIDENTFOX_TEAM_ID")
    if tenant_id and team_id:
        headers["X-Org-Id"] = tenant_id
        headers["X-Team-Node-Id"] = team_id
        return headers

    print(
        "Error: No auth configured. Need TEAM_TOKEN or "
        "INCIDENTFOX_TENANT_ID + INCIDENTFOX_TEAM_ID.",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="List K8s clusters for the current team"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    config_url = os.environ.get("CONFIG_SERVICE_URL")
    if not config_url:
        print("Error: CONFIG_SERVICE_URL not set.", file=sys.stderr)
        sys.exit(1)

    url = f"{config_url.rstrip('/')}/api/v1/team/k8s-clusters"
    headers = get_config_service_headers()

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)

        if response.status_code == 404:
            print("No K8s clusters configured for this team.")
            return

        if response.status_code >= 400:
            print(
                f"Error: config-service returned {response.status_code}: {response.text}",
                file=sys.stderr,
            )
            sys.exit(1)

        clusters = response.json()

    except httpx.ConnectError:
        print(
            f"Error: Cannot reach config-service at {config_url}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not clusters:
        print("No K8s clusters configured for this team.")
        return

    if args.json:
        print(json.dumps(clusters, indent=2))
    else:
        print(f"Clusters: {len(clusters)}")
        print()
        print(
            f"{'CLUSTER ID':<38} {'NAME':<25} {'STATUS':<14} {'K8S VERSION':<14} {'NODES':<6}"
        )
        print("-" * 97)
        for c in clusters:
            status = c.get("status", "unknown")
            indicator = {
                "connected": "+",
                "disconnected": "-",
                "error": "!",
            }.get(status, "?")
            print(
                f"{c.get('cluster_id', ''):<38} "
                f"{c.get('cluster_name', ''):<25} "
                f"{indicator} {status:<12} "
                f"{c.get('kubernetes_version') or '-':<14} "
                f"{c.get('node_count') or '-':<6}"
            )
        print()
        print(
            "Use --cluster-id <CLUSTER_ID> with other scripts to query a remote cluster."
        )


if __name__ == "__main__":
    main()
