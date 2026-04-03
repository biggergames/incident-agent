# IncidentFox - SRE Tools for Claude Code

You have access to **~100 DevOps & SRE tools** via the IncidentFox MCP server. These tools help with:

- **Kubernetes** - Pods, deployments, logs, events, resources
- **AWS** - EC2, CloudWatch, ECS, cost analysis
- **Observability** - Datadog, Prometheus, Grafana, Elasticsearch, Loki
- **Collaboration** - Slack, PagerDuty, GitHub
- **Analysis** - Anomaly detection, log analysis, blast radius

## Quick Start

Explore your infrastructure (try whichever applies):

```
Check my Kubernetes cluster health
Show my Grafana dashboards
```

## Real Work

Use these tools for actual tasks:

| Use Case | Example |
|----------|---------|
| **Alert Triage** | "Help me triage this alert: [paste]" |
| **Cost Optimization** | "Find AWS costs over the last month and explore reduction opportunities" |
| **CI/CD Debugging** | "Why did my GitHub Actions workflow fail? [paste url]" |
| **Log Analysis** | "Search logs for connection errors" |

## Configuration

Run `get_config_status` to see which integrations are configured. Missing credentials? Use `save_credential` to add them:

```
Save my Datadog API key: [key]
```

## Codebase

- **Services** (under `apps/`): account-service, gsm, leaderboard-service, live-ops, purchase-validator-service, team-service
- **Shared library**: `libs/common-lib/`

## Tech Stack

- **Language**: Java 21, microservices architecture
- **Orchestration**: Kubernetes on AWS EKS
- **Observability**: Grafana (dashboards + OTel traces via Tempo), OpenSearch (logs), CloudWatch (AWS metrics)
- **AWS Services**: API Gateway, DynamoDB, CloudWatch
- **Key Dashboard**: `bg-code` in Grafana (success/error graphs, CPU/memory/GC, external dependency metrics, per-pod request counts)

## Investigation Flow

When investigating an incident or alert:

1. **Start with Grafana** — check `bg-code` dashboard for success/error request counts
2. **Branch by alert type:**
   - **Error spike** → search error logs in OpenSearch
   - **Response time spike** → search Tempo for traces > 1s, check CPU/memory/GC graphs, check external dependency metrics, check request count across pods for load balancing issues
   - **AWS alarm** → check CloudWatch metrics, check if there is an active tournament/event
   - **Kubernetes issue** → check pod status, node health, resource usage
3. **Deep dive on slow traces**: find traces > 1s, identify the pod that served the request, check that pod's throttle status, CPU and memory usage from dashboards
4. **Correlate across systems** — e.g., slow DynamoDB span in a trace → check CloudWatch metrics for that DynamoDB table → check which pods were affected
5. **Check product context** if needed — active campaigns, events, trophy rush tournaments can explain traffic spikes

## Learn More

- Full docs: `local/claude_code_pack/README.md`
- 85+ tools reference in README
