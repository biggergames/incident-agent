"""Tempo distributed tracing tools.

Tools for searching traces and retrieving trace details via Grafana's datasource proxy.
Since Tempo typically runs inside a K8s cluster, this uses the Grafana proxy to avoid
requiring direct access or port-forwarding.

Requires: GRAFANA_URL, GRAFANA_API_KEY, and TEMPO_DATASOURCE_UID to be configured.
Alternatively, set TEMPO_URL for direct access (e.g., via port-forward).
"""

import json
from datetime import datetime, timedelta

import httpx
from mcp.server.fastmcp import FastMCP

from ..utils.config import get_env


def _get_tempo_client() -> tuple[httpx.Client, str]:
    """Get HTTP client and base path for Tempo API.

    Returns (client, base_path) where base_path is either:
    - "" for direct Tempo access
    - "/api/datasources/proxy/uid/{uid}" for Grafana proxy
    """
    tempo_url = get_env("TEMPO_URL")
    if tempo_url:
        return httpx.Client(base_url=tempo_url.rstrip("/"), timeout=30.0), ""

    grafana_url = get_env("GRAFANA_URL")
    grafana_api_key = get_env("GRAFANA_API_KEY")
    datasource_uid = get_env("TEMPO_DATASOURCE_UID")

    if not grafana_url or not grafana_api_key or not datasource_uid:
        missing = []
        if not grafana_url:
            missing.append("GRAFANA_URL")
        if not grafana_api_key:
            missing.append("GRAFANA_API_KEY")
        if not datasource_uid:
            missing.append("TEMPO_DATASOURCE_UID")
        raise ValueError(
            f"Tempo not configured. Missing: {', '.join(missing)}. "
            "Either set TEMPO_URL for direct access, or set GRAFANA_URL + "
            "GRAFANA_API_KEY + TEMPO_DATASOURCE_UID to use Grafana proxy."
        )

    api_key = grafana_api_key
    if ":" in api_key and not api_key.startswith("glsa_"):
        import base64
        credentials = base64.b64encode(api_key.encode()).decode()
        headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    client = httpx.Client(
        base_url=grafana_url.rstrip("/"),
        headers=headers,
        timeout=30.0,
    )
    base_path = f"/api/datasources/proxy/uid/{datasource_uid}"
    return client, base_path


def register_tools(mcp: FastMCP):
    """Register Tempo tools with the MCP server."""

    @mcp.tool()
    def tempo_search_traces(
        query: str = "{}",
        hours_ago: int = 1,
        min_duration: str = "",
        max_duration: str = "",
        limit: int = 20,
    ) -> str:
        """Search for traces using TraceQL.

        Args:
            query: TraceQL query (e.g., '{ duration > 1s }', '{ resource.service.name = "gsm" }',
                   '{ span.http.status_code >= 500 }')
            hours_ago: How far back to search (default: 1 hour)
            min_duration: Minimum trace duration (e.g., "100ms", "1s")
            max_duration: Maximum trace duration (e.g., "5s", "10s")
            limit: Maximum number of traces to return (default: 20)

        Returns:
            JSON with matching traces including trace IDs, durations, and service names.
        """
        try:
            client, base_path = _get_tempo_client()
        except ValueError as e:
            return json.dumps({"error": str(e)})

        try:
            now = datetime.utcnow()
            start = now - timedelta(hours=hours_ago)

            params = {
                "q": query,
                "start": str(int(start.timestamp())),
                "end": str(int(now.timestamp())),
                "limit": str(limit),
            }
            if min_duration:
                params["minDuration"] = min_duration
            if max_duration:
                params["maxDuration"] = max_duration

            with client:
                response = client.get(f"{base_path}/api/search", params=params)
                response.raise_for_status()
                data = response.json()

            traces = data.get("traces", [])

            formatted = []
            for trace in traces:
                formatted.append({
                    "trace_id": trace.get("traceID"),
                    "root_service": trace.get("rootServiceName"),
                    "root_operation": trace.get("rootTraceName"),
                    "duration_ms": round(trace.get("durationMs", 0), 2),
                    "span_count": trace.get("spanSets", [{}])[0].get("matched", 0) if trace.get("spanSets") else trace.get("spanCount", 0),
                    "start_time": datetime.fromtimestamp(
                        int(trace.get("startTimeUnixNano", 0)) / 1e9
                    ).isoformat() if trace.get("startTimeUnixNano") else None,
                })

            return json.dumps(
                {
                    "query": query,
                    "time_range": f"last {hours_ago} hour(s)",
                    "trace_count": len(formatted),
                    "traces": formatted,
                },
                indent=2,
            )

        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def tempo_get_trace(trace_id: str) -> str:
        """Get full trace details by trace ID.

        Args:
            trace_id: The trace ID to retrieve

        Returns:
            JSON with all spans in the trace including service names, operations,
            durations, and status codes.
        """
        if not trace_id:
            return json.dumps({"error": "trace_id is required"})

        try:
            client, base_path = _get_tempo_client()
        except ValueError as e:
            return json.dumps({"error": str(e)})

        try:
            with client:
                response = client.get(
                    f"{base_path}/api/traces/{trace_id}",
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

            batches = data.get("batches", [])
            spans = []

            # Key resource attributes to surface at span level
            _RESOURCE_KEYS = {"host.name", "service.instance.id", "service.version"}

            for batch in batches:
                resource = batch.get("resource", {})
                resource_attrs = {
                    a["key"]: a.get("value", {}).get("stringValue", a.get("value", {}).get("intValue", ""))
                    for a in resource.get("attributes", [])
                }
                service_name = resource_attrs.get("service.name", "unknown")
                host_name = resource_attrs.get("host.name", "")
                instance_id = resource_attrs.get("service.instance.id", "")

                for scope_span in batch.get("scopeSpans", []):
                    for span in scope_span.get("spans", []):
                        start_ns = int(span.get("startTimeUnixNano", 0))
                        end_ns = int(span.get("endTimeUnixNano", 0))
                        duration_ns = end_ns - start_ns
                        span_attrs = {
                            a["key"]: a.get("value", {}).get("stringValue", a.get("value", {}).get("intValue", ""))
                            for a in span.get("attributes", [])
                        }

                        span_data = {
                            "span_id": span.get("spanId"),
                            "parent_span_id": span.get("parentSpanId", ""),
                            "service": service_name,
                            "pod": host_name,
                            "operation": span.get("name"),
                            "start_time": datetime.fromtimestamp(start_ns / 1e9).isoformat(),
                            "start_ns": start_ns,
                            "duration_ms": round(duration_ns / 1e6, 2),
                            "status": span.get("status", {}).get("code", "UNSET"),
                            "kind": span.get("kind", ""),
                            "attributes": span_attrs,
                        }
                        if instance_id:
                            span_data["instance_id"] = instance_id
                        spans.append(span_data)

            # Sort by start time to show the natural waterfall order
            spans.sort(key=lambda s: s["start_ns"])

            # Calculate offset from trace start for each span
            if spans:
                trace_start_ns = spans[0]["start_ns"]
                for s in spans:
                    s["offset_ms"] = round((s["start_ns"] - trace_start_ns) / 1e6, 2)
                    del s["start_ns"]

            services = list(set(s["service"] for s in spans))
            pods = list(set(s["pod"] for s in spans if s.get("pod")))
            total_duration = max(s["duration_ms"] for s in spans) if spans else 0

            result = {
                "trace_id": trace_id,
                "span_count": len(spans),
                "total_duration_ms": total_duration,
                "services": services,
                "spans": spans[:50],
            }
            if pods:
                result["pods"] = pods

            return json.dumps(result, indent=2)

        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": str(e), "trace_id": trace_id})

    @mcp.tool()
    def tempo_list_tags() -> str:
        """List available trace tag names.

        Use to discover what attributes are available for filtering traces.

        Returns:
            JSON with available tag names.
        """
        try:
            client, base_path = _get_tempo_client()
        except ValueError as e:
            return json.dumps({"error": str(e)})

        try:
            with client:
                response = client.get(f"{base_path}/api/search/tags")
                response.raise_for_status()
                data = response.json()

            tag_names = data.get("tagNames", [])

            return json.dumps(
                {
                    "tag_count": len(tag_names),
                    "tags": sorted(tag_names),
                },
                indent=2,
            )

        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def tempo_tag_values(tag: str) -> str:
        """List values for a specific trace tag.

        Args:
            tag: Tag name (e.g., "service.name", "http.status_code")

        Returns:
            JSON with tag values.
        """
        if not tag:
            return json.dumps({"error": "tag is required"})

        try:
            client, base_path = _get_tempo_client()
        except ValueError as e:
            return json.dumps({"error": str(e)})

        try:
            with client:
                response = client.get(f"{base_path}/api/search/tag/{tag}/values")
                response.raise_for_status()
                data = response.json()

            values = data.get("tagValues", [])

            return json.dumps(
                {
                    "tag": tag,
                    "value_count": len(values),
                    "values": sorted(values),
                },
                indent=2,
            )

        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
