"""
Search Tool — Web search fallback when crawling fails.
Uses OpenAI Responses API with web search to find provider information.
"""

import json
import logging
import re

from openai import OpenAI

log = logging.getLogger("tool.search")

SEARCH_SYSTEM = """You research fintech API providers and extract structured data.
You have access to web search. Search for official documentation, pricing pages,
and developer resources. Only report what you find explicitly stated.
Respond ONLY with valid JSON, no markdown fences."""


class SearchTool:
    """Fallback: use OpenAI + web search when direct crawling fails."""

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    async def run(
        self,
        provider_name: str,
        provider_url: str,
        fields_needed: list[str],
    ) -> dict:
        """Search the web for provider information."""

        prompt = f"""Research "{provider_name}" ({provider_url}) and find:
{json.dumps(fields_needed, indent=2)}

Search their official website, documentation, and developer pages.
For each field, search specifically:
- capabilities: search "{provider_name} API features" and "{provider_name} documentation"
- supported_currencies: search "{provider_name} supported currencies"
- sdks: search "{provider_name} SDK libraries"
- pricing_indicative: search "{provider_name} pricing"
- api_spec_format: search "{provider_name} openapi swagger"

Return JSON:
{{
  "capabilities": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "supported_currencies": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "pricing_indicative": {{"values": {{"model": "...", "details": {{}}}}, "confidence": 0.0-1.0, "evidence": "..."}},
  "sdks": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "api_spec_format": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}}
}}"""

        try:
            resp = self.client.responses.create(
                model=self.model,
                max_output_tokens=4096,
                tools=[{"type": "web_search"}],
                text={"format": {"type": "json_object"}},
                input=[
                    {"role": "system", "content": SEARCH_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )

            text = (resp.output_text or "").strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            return json.loads(text)

        except json.JSONDecodeError as e:
            log.error(f"Search result JSON parse error: {e}")
            return {}
        except Exception as e:
            log.error(f"Search tool error: {e}")
            return {}
