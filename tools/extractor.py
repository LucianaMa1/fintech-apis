"""
Extractor Tool — LLM-based structured data extraction.
"""

import json
import logging
import re

from openai import OpenAI

log = logging.getLogger("tool.extract")

SYSTEM_PROMPT = """You are an API intelligence analyst extracting structured data about fintech API providers.

RULES:
1. Only extract what is EXPLICITLY stated. Never infer or guess.
2. Rate confidence 0.0-1.0 per field. Below 0.5 = use null.
3. Use the controlled vocabulary for capabilities when possible.
4. For pricing, capture the structure (%, flat fee, tiers), not just "custom".

CONTROLLED VOCABULARY — CAPABILITIES:
Payment rails: card_payment_online, card_payment_in_store, ach_debit, ach_credit, ach_same_day, sepa_direct_debit, sepa_credit_transfer, bacs_debit, faster_payments_uk, wire_transfer_domestic, wire_transfer_international, real_time_payments_rtp, swift
Wallets: apple_pay, google_pay, wechat_pay, alipay, paypal
BNPL: klarna, afterpay, affirm
Card issuing: card_issuing_virtual, card_issuing_physical, card_issuing_tokenized, push_provisioning_apple_pay, push_provisioning_google_pay, card_controls_spend_limits, card_controls_merchant_category, card_controls_velocity, just_in_time_funding, pin_management
Banking: checking_account_creation, savings_account_creation, fdic_insured_deposits, book_transfer_internal, check_deposit_remote, bill_pay
Identity/KYC: identity_verification_document, identity_verification_selfie, kyc_cip_verification, account_ownership_verification
Open banking: bank_account_linking, account_balance_realtime, transaction_history, transaction_categorization, income_verification, employment_verification, instant_account_verification, payment_initiation_single, payment_initiation_recurring
Fraud/Risk: fraud_scoring_realtime, risk_scoring, device_fingerprinting, behavioral_biometrics, aml_watchlist_screening, sanctions_screening, transaction_monitoring, bot_detection
Market data: stock_price_realtime, stock_price_historical_daily, stock_price_intraday, forex_rate_realtime, crypto_price_realtime, technical_indicators_sma, fundamental_data_earnings
Trading: stock_trading_us, options_trading, crypto_trading, fractional_shares
Other: tokenization, 3ds_authentication, network_tokens, recurring_billing, subscription_management, invoicing, hosted_payment_page, split_payments, multi_currency_processing, tax_calculation, webhook_notifications

Respond ONLY with valid JSON. No markdown fences, no preamble."""


def _build_user_prompt(
    provider_name: str,
    provider_url: str,
    pages: list[dict],
    target_fields: list[str] = None,
) -> str:
    page_sections = []
    for i, p in enumerate(pages):
        page_sections.append(
            f"=== PAGE {i+1}: {p.get('title','')} ===\n"
            f"URL: {p['url']}\n"
            f"CONTENT:\n{p['text'][:10000]}\n"
        )
    pages_block = "\n\n".join(page_sections)

    fields_note = ""
    if target_fields:
        fields_note = (
            f"\nFOCUS ONLY on these fields: {', '.join(target_fields)}\n"
            "Return null for all other fields.\n"
        )

    return f"""Analyze pages from "{provider_name}" ({provider_url}).
{fields_note}
{pages_block}

---

Extract into this JSON:
{{
  "capabilities": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "supported_currencies": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "pricing_indicative": {{"values": {{"model": "...", "details": {{}}}}, "confidence": 0.0-1.0, "evidence": "..."}},
  "sdks": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "api_spec_format": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "supported_payment_rails": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}},
  "compliance_certifications": {{"values": [...], "confidence": 0.0-1.0, "evidence": "..."}}
}}"""


class ExtractorTool:
    """Uses OpenAI to extract structured data from crawled pages."""

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def run(
        self,
        provider_name: str,
        provider_url: str,
        pages: list[dict],
        target_fields: list[str] = None,
        strict_mode: bool = False,
    ) -> dict:
        """Extract structured data from crawled pages via LLM."""

        if not pages:
            return {}

        # Batch pages (5 per LLM call)
        all_results = []
        batch_size = 5

        for i in range(0, len(pages), batch_size):
            batch = pages[i : i + batch_size]
            prompt = _build_user_prompt(
                provider_name, provider_url, batch, target_fields
            )

            system = SYSTEM_PROMPT
            if strict_mode:
                system += (
                    "\n\nSTRICT MODE: Be extra conservative. "
                    "Only include data you are 80%+ confident about. "
                    "Respond with syntactically perfect JSON."
                )

            try:
                resp = self.client.responses.create(
                    model=self.model,
                    max_output_tokens=4096,
                    text={"format": {"type": "json_object"}},
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                )

                text = (resp.output_text or "").strip()
                text = re.sub(r"^```json\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                result = json.loads(text)
                all_results.append(result)

            except json.JSONDecodeError as e:
                log.error(f"JSON parse error: {e}")
            except Exception as e:
                log.error(f"LLM error: {e}")

        if not all_results:
            return {}

        # Merge batches
        return self._merge(all_results) if len(all_results) > 1 else all_results[0]

    def _merge(self, results: list[dict]) -> dict:
        merged = {}
        list_fields = [
            "capabilities", "supported_currencies", "sdks",
            "api_spec_format", "supported_payment_rails",
            "compliance_certifications",
        ]

        for field in list_fields:
            all_vals = set()
            max_conf = 0.0
            evidence_parts = []

            for r in results:
                if field in r and r[field].get("values"):
                    vals = r[field]["values"]
                    if isinstance(vals, list):
                        all_vals.update(vals)
                    max_conf = max(max_conf, r[field].get("confidence", 0))
                    ev = r[field].get("evidence", "")
                    if ev:
                        evidence_parts.append(ev)

            merged[field] = {
                "values": sorted(all_vals) if all_vals else None,
                "confidence": max_conf,
                "evidence": " | ".join(evidence_parts),
            }

        # Pricing: take highest confidence
        best_pricing = None
        best_conf = 0
        for r in results:
            if "pricing_indicative" in r:
                conf = r["pricing_indicative"].get("confidence", 0)
                if conf > best_conf:
                    best_pricing = r["pricing_indicative"]
                    best_conf = conf
        if best_pricing:
            merged["pricing_indicative"] = best_pricing

        return merged
