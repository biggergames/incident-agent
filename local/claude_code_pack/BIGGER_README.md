# IncidentFox Claude Code Plugin — Team Setup

We use the [IncidentFox](https://incidentfox.ai) Claude Code plugin for SRE investigations. This repo is a customized fork with our additions.

## What we changed

- **Added Tempo (tracing) datasource** — 4 new tools: `tempo_search_traces`, `tempo_get_trace`, `tempo_list_tags`, `tempo_tag_values`. Works via Grafana datasource proxy (no port-forward needed). Requires `TEMPO_DATASOURCE_UID` in `.env`.
- **Updated `CLAUDE.md`** with our codebase context, tech stack, and investigation flow.
- **Fixed `plugin.json`** path formats for skills/commands/hooks.

## Setup

1. Install [uv](https://github.com/astral-sh/uv) and [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) if you don't have them.

2. Run the install script:
   ```bash
   ./install.sh
   ```

3. Create `.env` with your credentials:
   ```bash
   # Required
   GRAFANA_URL=<our grafana url>
   GRAFANA_API_KEY=<your grafana api key>
   TEMPO_DATASOURCE_UID=<tempo datasource uid from grafana>
   AWS_REGION=us-east-1

   # Optional (add as needed)
   DATADOG_API_KEY=
   DATADOG_APP_KEY=
   GITHUB_TOKEN=
   SLACK_BOT_TOKEN=
   PAGERDUTY_API_KEY=
   ```

4. Run:
   ```bash
   claude --plugin-dir /path/to/this/repo
   ```

## Investigation learnings

Things we learned from past investigations that Claude should know. These are saved in Claude's memory system but listed here for the team.

- **Timestamps are UTC+3** — All Grafana/Tempo timestamps are Turkey time, not UTC. Always convert when correlating.
- **Narrow Grafana queries** — Filter by app/service name, use short time ranges (1-2h), keep step small (1m). Large steps hide spikes. Don't increase step to avoid token limits.
- **AWS credentials from .env** — MCP tools read from `.env`, not your shell AWS profile. If queries return empty, it's wrong region or wrong table name — debug, don't move on.
- **Verify resource names** — Don't guess DynamoDB table names from alert names (e.g., alert says `GameState`, table is `Prod.GameState`). Look up the actual name first.
- **You decide when investigation is done** — Claude will try to wrap up and summarize. Don't let it. Keep pushing until you're satisfied.
- **Verify Claude's numbers** — If it claims "X spiked to 4.12 at 03:30", ask for raw data. It can misread timestamps or cherry-pick baselines.
- **`created_new_account_total`** — Prometheus counter on account-service. Check with `sum(increase(created_new_account_total{bg_env="prod"}[5m]))` when you see DynamoDB write spikes or cache miss storms. New signups cause cascading writes + cache misses.
