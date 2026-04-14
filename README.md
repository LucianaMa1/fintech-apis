# API Intelligence Agent

An autonomous agent that continuously discovers, crawls, extracts, and validates fintech API provider data — hosted free on GitHub Actions.

## Agent vs Script

This is **not** a cron script. It's an agent with:

| Trait | Script | This Agent |
|-------|--------|------------|
| Decision-making | Run same steps every time | Plans based on what's stale/broken |
| Error handling | Fail and stop | Retry with different strategy |
| State | Stateless between runs | Remembers failures, tracks confidence |
| Resource use | Processes everything every time | Skips unchanged content (hash-based) |
| Self-correction | None | Switches tools when one fails |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  AGENT LOOP (every 6h)                  │
│                                                         │
│  ┌──────────┐    ┌──────┐    ┌─────┐    ┌─────────┐   │
│  │ 1.OBSERVE│───▶│2.PLAN│───▶│3.ACT│───▶│4.REFLECT│   │
│  │          │    │      │    │     │    │         │   │
│  │ What's   │    │ Pick │    │ Run │    │ Did it  │   │
│  │ stale?   │    │ tasks│    │tools│    │ work?   │   │
│  │ broken?  │    │ by   │    │     │    │ Update  │   │
│  │ missing? │    │ prio │    │     │    │ memory  │   │
│  └──────────┘    └──────┘    └──┬──┘    └────┬────┘   │
│                                 │             │        │
│                          ┌──────┴──────┐  ┌───┴───┐   │
│                          │   5 TOOLS   │  │PERSIST│   │
│                          │             │  │git    │   │
│                          │ ·crawl      │  │commit │   │
│                          │ ·extract    │  └───────┘   │
│                          │ ·validate   │              │
│                          │ ·search     │              │
│                          │ ·parse_spec │              │
│                          └─────────────┘              │
└─────────────────────────────────────────────────────────┘
```

## The 5-Phase Loop

**OBSERVE** — Loads the catalog and checks each provider: never verified? stale? low confidence? failed last time? Produces a situation report.

**PLAN** — Prioritizes tasks: (1) new providers, (2) failed retries with different strategy, (3) low-confidence targeted re-extraction, (4) routine refresh. Caps at 15 providers per run.

**ACT** — Executes each task using the right tool chain:
- `full_discovery`: crawl → parse spec → LLM extract → validate
- `refresh`: crawl → check content hashes → skip if unchanged
- `targeted_extraction`: crawl → extract only low-confidence fields
- `search_fallback`: OpenAI + web search when crawling fails
- `crawl_with_playwright`: retry with headless browser for JS-heavy docs

**REFLECT** — Counts successes/failures, logs errors, identifies patterns.

**PERSIST** — Saves catalog + memory to disk, git commits for GitHub Actions persistence.

## Self-Correction

When a provider fails, the agent doesn't just retry the same way:

| Failure type | Retry strategy |
|---|---|
| Crawl timeout | `crawl_with_playwright` (headless browser) |
| Crawl returns 0 pages | `search_fallback` (web search) |
| LLM returns bad JSON | `extract_strict` (tighter prompt) |
| 3+ failures | Marked `needs_human_review` |

## Free Hosting: GitHub Actions

The agent runs on GitHub Actions' free tier:
- **Schedule**: Every 6 hours (cron `0 */6 * * *`)
- **Budget**: ~20 min per run × 4 runs/day = 80 min/day, well within 2000 min/month free
- **State**: Persisted via git commits to the repo itself (`data/` and `memory/` directories)
- **Manual trigger**: `workflow_dispatch` with optional provider filter

## Setup

### 1. Create GitHub repo

```bash
cd /path/to/api-intel-agent
git init
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/api-intel-agent.git
```

### 2. Add your OpenAI API key

Go to **Settings → Secrets and variables → Actions → New repository secret**

Name: `OPENAI_API_KEY`
Value: `sk-proj-...`

Optional:

Go to **Settings → Secrets and variables → Actions → Variables → New repository variable**

Name: `OPENAI_MODEL`
Value: `gpt-4.1-mini` or `gpt-4.1`

### 3. Seed the catalog

Edit `data/catalog.json` to add providers. Minimum fields:

```json
{"id": "stripe", "name": "Stripe", "website": "https://stripe.com", "docs": "https://docs.stripe.com/api"}
```

### 4. Push and let it run

```bash
git add .
git commit -m "initial setup"
git push -u origin main
```

The agent will:
- Run immediately (push trigger on `data/catalog.json`)
- Then every 6 hours on schedule
- Process all unverified providers first, then routine refreshes

### 5. Manual trigger

Go to **Actions → API Intelligence Agent → Run workflow**

Options:
- **provider**: Process only one provider (e.g., `stripe`)
- **force_refresh**: Re-verify everything regardless of staleness

## Project Structure

```
api-intel-agent/
├── .github/workflows/
│   └── agent.yml          # GitHub Actions — runs every 6h
├── agent/
│   └── core.py            # The agent brain — observe/plan/act/reflect/persist
├── tools/
│   ├── crawler.py         # Web page discovery + content extraction
│   ├── extractor.py       # OpenAI-based structured data extraction
│   ├── validator.py       # Multi-source reconciliation
│   ├── search.py          # OpenAI web search fallback
│   └── openapi_parser.py  # OpenAPI spec → capabilities
├── memory/
│   ├── state.py           # Persistent state management
│   ├── run_history.json   # Log of every agent run
│   └── retries.json       # Per-provider retry tracking
├── data/
│   └── catalog.json       # The verified API catalog (agent output)
├── requirements.txt
└── README.md
```

## Adding New Providers

Just add a new entry to `data/catalog.json`:

```json
{"id": "my-api", "name": "My API", "website": "https://myapi.com", "docs": "https://docs.myapi.com"}
```

Push, and the agent will pick it up on the next run (priority 1: never verified).

## Monitoring

Check `memory/run_history.json` for run summaries:

```json
{
  "total_tasks": 5,
  "successes": 4,
  "failures": 1,
  "no_changes": 2,
  "errors": [{"provider": "finicity", "error": "crawl timeout"}],
  "timestamp": "2026-04-13T12:00:00Z"
}
```

Check `memory/retries.json` for persistent failures:

```json
{
  "finicity": {
    "count": 2,
    "last_error": "crawl timeout",
    "errors": [...]
  }
}
```

## Cost Estimate

- **GitHub Actions**: Free (public repo, ~80 min/day)
- **OpenAI API**: Varies by chosen model and provider count
  - 13 providers × ~5 pages × ~3000 tokens/page = ~200K input tokens
  - Default model is `gpt-4.1-mini`; you can override it with `OPENAI_MODEL`
  - 4 runs/day is still practical because the agent skips unchanged pages
- **Optimization**: `refresh` action skips LLM calls when content unchanged, typically cutting costs 50-70%

## Extending

### Add new tools
Create a new file in `tools/`, then register it in `agent/core.py`:
```python
self.tools["my_tool"] = MyTool()
```

### Add new fields to extract
1. Update the controlled vocabulary in `tools/extractor.py`
2. Add the field to the extraction prompt
3. Add validation logic in `tools/validator.py`

### Change scheduling
Edit `.github/workflows/agent.yml` cron expression:
```yaml
schedule:
  - cron: '0 */3 * * *'  # every 3 hours
```
