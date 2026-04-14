"""
API Intelligence Agent — Core Loop
====================================
An autonomous agent that continuously discovers, crawls, extracts,
and validates fintech API provider data.

This is NOT a script. It's an agent with:
- A planning phase (decide what to do next)
- Tool selection (pick the right action)
- Memory (persist state, learn from failures)
- Self-correction (retry with different strategies)
- Continuous execution (sleep when idle, wake on schedule)

Hosted free on GitHub Actions (2000 min/month).
State persisted via git commits to the repo itself.
"""

import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from tools.crawler import CrawlerTool
from tools.extractor import ExtractorTool
from tools.validator import ValidatorTool
from tools.search import SearchTool
from tools.openapi_parser import OpenAPIParserTool
from memory.state import AgentMemory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-12s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent")


# ─── Agent Configuration ────────────────────────────────────────────────────

class AgentConfig:
    """Agent behavior configuration."""

    # How often to re-verify a provider (days)
    REFRESH_INTERVAL_DAYS = 7

    # How many providers to process per run
    # (GitHub Actions has a 6-hour timeout, budget ~20 min per provider)
    MAX_PROVIDERS_PER_RUN = 15

    # Confidence threshold below which we flag for re-extraction
    LOW_CONFIDENCE_THRESHOLD = 0.6

    # Max retries per provider before marking as "needs_human_review"
    MAX_RETRIES = 3

    # Pause between providers (seconds) — be polite to servers
    POLITENESS_DELAY = 5

    # Max pages to crawl per provider
    MAX_PAGES = 25

    # OpenAI model to use
    MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


# ─── The Agent ──────────────────────────────────────────────────────────────

class APIIntelAgent:
    """
    Autonomous agent that maintains an API intelligence catalog.

    The agent loop:
    1. OBSERVE  — load memory, check what's stale/missing/broken
    2. PLAN     — decide which providers to process, in what order
    3. ACT      — for each provider, pick and execute tools
    4. REFLECT  — evaluate results, update confidence, note failures
    5. PERSIST  — save state, commit to git
    """

    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig()
        self.memory = AgentMemory()

        # Initialize tools
        api_key = os.environ.get("OPENAI_API_KEY", "")
        self.tools = {
            "crawl": CrawlerTool(max_pages=self.config.MAX_PAGES),
            "extract": ExtractorTool(api_key=api_key, model=self.config.MODEL),
            "validate": ValidatorTool(),
            "search": SearchTool(api_key=api_key, model=self.config.MODEL),
            "parse_openapi": OpenAPIParserTool(),
        }

        self.run_log: list[dict] = []

    # ─── Phase 1: OBSERVE ───────────────────────────────────────────────

    def observe(self) -> dict:
        """
        Assess the current state of the catalog.
        Returns a situation report the planner can act on.
        """
        log.info("👁  OBSERVE — assessing catalog state")

        catalog = self.memory.load_catalog()
        history = self.memory.load_run_history()
        now = datetime.now(timezone.utc)

        situation = {
            "total_providers": len(catalog),
            "never_verified": [],
            "stale": [],
            "low_confidence": [],
            "failed_last_run": [],
            "recently_verified": [],
            "needs_human_review": [],
        }

        for entry in catalog:
            pid = entry["id"]
            meta = entry.get("_meta", {})
            last_verified = meta.get("last_verified")
            error = meta.get("error")
            retry_count = self.memory.get_retry_count(pid)

            # Too many failures — escalate
            if retry_count >= self.config.MAX_RETRIES:
                situation["needs_human_review"].append({
                    "id": pid,
                    "reason": f"Failed {retry_count} times",
                    "last_error": self.memory.get_last_error(pid),
                })
                continue

            # Never verified
            if not last_verified:
                situation["never_verified"].append(pid)
                continue

            # Check staleness
            try:
                verified_date = datetime.fromisoformat(last_verified)
                if verified_date.tzinfo is None:
                    verified_date = datetime.strptime(last_verified, "%Y-%m-%d")
                    verified_date = verified_date.replace(tzinfo=timezone.utc)
                age_days = (now - verified_date).days
            except (ValueError, TypeError):
                situation["never_verified"].append(pid)
                continue

            if age_days > self.config.REFRESH_INTERVAL_DAYS:
                situation["stale"].append({"id": pid, "age_days": age_days})
            else:
                situation["recently_verified"].append(pid)

            # Check confidence
            confidences = meta.get("confidence", {})
            low_fields = [
                f for f, c in confidences.items()
                if isinstance(c, (int, float)) and c < self.config.LOW_CONFIDENCE_THRESHOLD
            ]
            if low_fields:
                situation["low_confidence"].append({
                    "id": pid,
                    "low_fields": low_fields,
                })

            # Check if failed last run
            if error:
                situation["failed_last_run"].append({
                    "id": pid,
                    "error": error,
                })

        log.info(
            f"   Catalog: {situation['total_providers']} providers | "
            f"Never verified: {len(situation['never_verified'])} | "
            f"Stale: {len(situation['stale'])} | "
            f"Low confidence: {len(situation['low_confidence'])} | "
            f"Failed: {len(situation['failed_last_run'])}"
        )

        return situation

    # ─── Phase 2: PLAN ──────────────────────────────────────────────────

    def plan(self, situation: dict) -> list[dict]:
        """
        Decide what to do this run.
        Returns an ordered task list.

        Priority:
        1. Never-verified providers (new entries)
        2. Failed providers (retry with different strategy)
        3. Low-confidence fields (targeted re-extraction)
        4. Stale providers (routine refresh)
        """
        log.info("🧠 PLAN — deciding what to do")

        tasks = []

        # Priority 1: Never verified
        for pid in situation["never_verified"]:
            tasks.append({
                "provider_id": pid,
                "action": "full_discovery",
                "reason": "never verified",
                "priority": 1,
            })

        # Priority 2: Failed last run — retry with different strategy
        for item in situation["failed_last_run"]:
            retry_count = self.memory.get_retry_count(item["id"])
            strategy = self._pick_retry_strategy(retry_count, item["error"])
            tasks.append({
                "provider_id": item["id"],
                "action": strategy,
                "reason": f"retry #{retry_count + 1}: {item['error']}",
                "priority": 2,
            })

        # Priority 3: Low confidence — targeted re-extraction
        for item in situation["low_confidence"]:
            tasks.append({
                "provider_id": item["id"],
                "action": "targeted_extraction",
                "target_fields": item["low_fields"],
                "reason": f"low confidence on: {', '.join(item['low_fields'])}",
                "priority": 3,
            })

        # Priority 4: Stale — routine refresh
        stale_sorted = sorted(
            situation["stale"], key=lambda x: x["age_days"], reverse=True
        )
        for item in stale_sorted:
            tasks.append({
                "provider_id": item["id"],
                "action": "refresh",
                "reason": f"stale ({item['age_days']} days old)",
                "priority": 4,
            })

        # Enforce per-run limit
        tasks = tasks[: self.config.MAX_PROVIDERS_PER_RUN]

        log.info(f"   Planned {len(tasks)} tasks for this run:")
        for t in tasks:
            log.info(f"   [{t['priority']}] {t['provider_id']}: {t['action']} — {t['reason']}")

        return tasks

    def _pick_retry_strategy(self, retry_count: int, last_error: str) -> str:
        """Pick a different strategy based on what failed."""
        if "crawl" in str(last_error).lower() or "timeout" in str(last_error).lower():
            # Crawling failed — try with playwright or search fallback
            if retry_count == 0:
                return "crawl_with_playwright"
            else:
                return "search_fallback"
        elif "json" in str(last_error).lower() or "parse" in str(last_error).lower():
            # LLM output was malformed — retry with stricter prompt
            return "extract_strict"
        else:
            # Generic retry
            return "full_discovery"

    # ─── Phase 3: ACT ───────────────────────────────────────────────────

    async def act(self, tasks: list[dict]) -> list[dict]:
        """
        Execute the planned tasks.
        Each task is a provider + action + strategy.
        """
        log.info("⚡ ACT — executing tasks")
        results = []

        for i, task in enumerate(tasks):
            pid = task["provider_id"]
            action = task["action"]

            log.info(f"\n{'─'*50}")
            log.info(f"Task {i+1}/{len(tasks)}: {pid} → {action}")
            log.info(f"{'─'*50}")

            try:
                entry = self.memory.get_provider(pid)
                if not entry:
                    log.error(f"Provider {pid} not found in catalog")
                    continue

                result = await self._execute_action(entry, action, task)
                results.append({
                    "provider_id": pid,
                    "action": action,
                    "status": "success",
                    "result": result,
                })

                # Reset retry count on success
                self.memory.reset_retries(pid)

            except Exception as e:
                log.error(f"Task failed: {e}")
                log.debug(traceback.format_exc())
                results.append({
                    "provider_id": pid,
                    "action": action,
                    "status": "error",
                    "error": str(e),
                })
                self.memory.increment_retries(pid, str(e))

            # Politeness delay
            if i < len(tasks) - 1:
                log.info(f"   Waiting {self.config.POLITENESS_DELAY}s...")
                time.sleep(self.config.POLITENESS_DELAY)

        return results

    async def _execute_action(self, entry: dict, action: str, task: dict) -> dict:
        """Route to the right tool chain based on the action."""

        if action == "full_discovery":
            return await self._full_discovery(entry)

        elif action == "refresh":
            return await self._refresh(entry)

        elif action == "targeted_extraction":
            return await self._targeted_extraction(
                entry, task.get("target_fields", [])
            )

        elif action == "search_fallback":
            return await self._search_fallback(entry)

        elif action == "crawl_with_playwright":
            return await self._full_discovery(entry, use_playwright=True)

        elif action == "extract_strict":
            return await self._full_discovery(entry, strict_mode=True)

        else:
            return await self._full_discovery(entry)

    async def _full_discovery(
        self, entry: dict, use_playwright: bool = False, strict_mode: bool = False
    ) -> dict:
        """Full pipeline: crawl → parse spec → extract → validate → save."""
        pid = entry["id"]
        name = entry["name"]

        # Step 1: Crawl
        log.info(f"  [1/4] Crawling {entry['website']}")
        pages = await self.tools["crawl"].run(
            website=entry["website"],
            docs_url=entry["docs"],
            use_playwright=use_playwright,
        )

        if not pages:
            raise RuntimeError(f"Crawl returned 0 pages for {name}")

        log.info(f"  [1/4] Got {len(pages)} pages")

        # Step 2: Check for OpenAPI spec
        openapi_data = {}
        openapi_url = None
        for page in pages:
            if page.get("is_spec"):
                log.info(f"  [2/4] Found OpenAPI spec at {page['url']}")
                openapi_url = page["url"]
                openapi_data = self.tools["parse_openapi"].run(page["text"])
                break

        if not openapi_data:
            log.info(f"  [2/4] No OpenAPI spec found, skipping")

        # Step 3: LLM extraction
        log.info(f"  [3/4] Extracting structured data via LLM")
        text_pages = [p for p in pages if not p.get("is_spec")]
        extracted = self.tools["extract"].run(
            provider_name=name,
            provider_url=entry["website"],
            pages=text_pages,
            strict_mode=strict_mode,
        )

        # Step 4: Validate and reconcile
        log.info(f"  [4/4] Validating and reconciling")
        validated = self.tools["validate"].run(
            extracted=extracted,
            openapi_data=openapi_data,
            existing=entry,
        )

        # Build final entry
        updated = self._merge_entry(entry, validated, pages, openapi_url)
        self.memory.save_provider(pid, updated)

        return {
            "pages_crawled": len(pages),
            "has_openapi_spec": bool(openapi_data),
            "fields_updated": list(validated.keys()),
        }

    async def _refresh(self, entry: dict) -> dict:
        """
        Refresh: re-crawl and check for changes.
        Only re-extract if content hash changed.
        """
        pid = entry["id"]
        old_hashes = entry.get("_meta", {}).get("content_hashes", {})

        # Crawl
        pages = await self.tools["crawl"].run(
            website=entry["website"],
            docs_url=entry["docs"],
        )

        if not pages:
            raise RuntimeError(f"Refresh crawl returned 0 pages for {entry['name']}")

        # Check if anything changed
        new_hashes = {p["url"]: p["content_hash"] for p in pages}
        changed = any(
            new_hashes.get(url) != old_hashes.get(url)
            for url in set(list(new_hashes.keys()) + list(old_hashes.keys()))
        )

        if not changed:
            log.info(f"  No content changes detected, bumping verified date only")
            entry.setdefault("_meta", {})["last_verified"] = (
                datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
            entry["_meta"]["content_hashes"] = new_hashes
            self.memory.save_provider(pid, entry)
            return {"status": "no_changes", "pages_checked": len(pages)}

        log.info(f"  Content changed! Re-running full extraction")
        return await self._full_discovery(entry)

    async def _targeted_extraction(
        self, entry: dict, target_fields: list[str]
    ) -> dict:
        """Re-extract only specific low-confidence fields."""
        pages = await self.tools["crawl"].run(
            website=entry["website"],
            docs_url=entry["docs"],
        )

        extracted = self.tools["extract"].run(
            provider_name=entry["name"],
            provider_url=entry["website"],
            pages=[p for p in pages if not p.get("is_spec")],
            target_fields=target_fields,
        )

        validated = self.tools["validate"].run(
            extracted=extracted,
            openapi_data={},
            existing=entry,
        )

        updated = self._merge_entry(entry, validated, pages)
        self.memory.save_provider(entry["id"], updated)

        return {
            "target_fields": target_fields,
            "fields_updated": list(validated.keys()),
        }

    async def _search_fallback(self, entry: dict) -> dict:
        """When crawling fails, use web search to find information."""
        log.info(f"  Using web search fallback for {entry['name']}")

        extracted = await self.tools["search"].run(
            provider_name=entry["name"],
            provider_url=entry["website"],
            fields_needed=[
                "capabilities", "supported_currencies", "sdks",
                "pricing_indicative", "api_spec_format",
            ],
        )

        validated = self.tools["validate"].run(
            extracted=extracted,
            openapi_data={},
            existing=entry,
        )

        updated = self._merge_entry(entry, validated, [], source="web_search")
        self.memory.save_provider(entry["id"], updated)

        return {"method": "web_search", "fields_updated": list(validated.keys())}

    def _merge_entry(
        self, existing: dict, validated: dict, pages: list,
        openapi_url: str = None, source: str = "crawl+llm"
    ) -> dict:
        """Merge validated data into existing entry."""
        updated = dict(existing)

        for field_name, field_data in validated.items():
            if field_data.get("value") is not None:
                updated[field_name] = field_data["value"]

        # Update metadata
        meta = updated.setdefault("_meta", {})
        meta["last_verified"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        meta["verification_method"] = source
        meta["pages_crawled"] = len(pages)

        if openapi_url:
            meta["openapi_spec_url"] = openapi_url

        # Confidence scores
        meta["confidence"] = {
            field: data.get("confidence", 0)
            for field, data in validated.items()
        }

        # Source tracking
        meta["sources"] = {
            field: {
                "method": data.get("method", source),
                "evidence": data.get("evidence", ""),
            }
            for field, data in validated.items()
        }

        # Content hashes for change detection
        meta["content_hashes"] = {
            p["url"]: p["content_hash"]
            for p in pages
            if "content_hash" in p
        }

        return updated

    # ─── Phase 4: REFLECT ───────────────────────────────────────────────

    def reflect(self, results: list[dict]) -> dict:
        """
        Evaluate the run.
        Log statistics, identify patterns, adjust strategy.
        """
        log.info("\n🪞 REFLECT — evaluating run")

        summary = {
            "total_tasks": len(results),
            "successes": 0,
            "failures": 0,
            "no_changes": 0,
            "errors": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for r in results:
            if r["status"] == "success":
                summary["successes"] += 1
                if r.get("result", {}).get("status") == "no_changes":
                    summary["no_changes"] += 1
            else:
                summary["failures"] += 1
                summary["errors"].append({
                    "provider": r["provider_id"],
                    "error": r.get("error", "unknown"),
                })

        log.info(
            f"   Results: {summary['successes']} success, "
            f"{summary['failures']} failures, "
            f"{summary['no_changes']} unchanged"
        )

        if summary["errors"]:
            log.warning("   Errors:")
            for e in summary["errors"]:
                log.warning(f"     {e['provider']}: {e['error']}")

        return summary

    # ─── Phase 5: PERSIST ───────────────────────────────────────────────

    def persist(self, run_summary: dict):
        """Save all state and commit to git."""
        log.info("💾 PERSIST — saving state")

        # Save run history
        self.memory.append_run_history(run_summary)

        # Save catalog
        self.memory.save_catalog()

        # Git commit (for GitHub Actions persistence)
        if os.environ.get("GITHUB_ACTIONS"):
            self._git_commit(run_summary)

        log.info("   State saved successfully")

    def _git_commit(self, summary: dict):
        """Commit updated catalog to git."""
        import subprocess

        try:
            successes = summary["successes"]
            failures = summary["failures"]
            msg = (
                f"agent: verified {successes} providers "
                f"({failures} failures) — "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )

            subprocess.run(["git", "config", "user.name", "API Intel Agent"], check=True)
            subprocess.run(["git", "config", "user.email", "agent@api-intel.bot"], check=True)
            subprocess.run(["git", "add", "data/", "memory/"], check=True)
            subprocess.run(["git", "commit", "-m", msg], check=True)
            subprocess.run(["git", "push"], check=True)
            log.info(f"   Git commit: {msg}")

        except subprocess.CalledProcessError as e:
            log.warning(f"   Git commit failed: {e}")

    # ─── Main Agent Loop ────────────────────────────────────────────────

    async def run(self):
        """
        Execute one full agent cycle:
        OBSERVE → PLAN → ACT → REFLECT → PERSIST
        """
        log.info("=" * 60)
        log.info("🤖 API Intelligence Agent — starting run")
        log.info(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        log.info("=" * 60)

        start_time = time.time()

        try:
            # Phase 1: Observe
            situation = self.observe()

            # Phase 2: Plan
            tasks = self.plan(situation)

            if not tasks:
                log.info("✅ Nothing to do — catalog is up to date!")
                self.persist({
                    "total_tasks": 0,
                    "successes": 0,
                    "failures": 0,
                    "no_changes": 0,
                    "errors": [],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "note": "all providers up to date",
                })
                return

            # Phase 3: Act
            results = await self.act(tasks)

            # Phase 4: Reflect
            summary = self.reflect(results)

            # Phase 5: Persist
            self.persist(summary)

        except Exception as e:
            log.error(f"Agent run failed: {e}")
            log.error(traceback.format_exc())
            self.persist({
                "total_tasks": 0,
                "successes": 0,
                "failures": 1,
                "errors": [{"provider": "agent", "error": str(e)}],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        elapsed = time.time() - start_time
        log.info(f"\n🏁 Run complete in {elapsed:.0f}s")


# ─── Entry Point ────────────────────────────────────────────────────────────

async def main():
    agent = APIIntelAgent()
    await agent.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
