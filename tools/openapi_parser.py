"""
OpenAPI Parser Tool — Extract capabilities from OpenAPI/Swagger specs.
Highest confidence data source (programmatic, not LLM).
"""

import json
import logging

log = logging.getLogger("tool.openapi")

CAPABILITY_MAP = {
    "payment": "card_payment_online",
    "charge": "card_payment_online",
    "refund": "refund_processing",
    "payout": "payouts_bank_transfer",
    "transfer": "book_transfer_internal",
    "customer": "customer_management",
    "subscription": "subscription_management",
    "invoice": "invoicing",
    "token": "tokenization",
    "identity": "identity_verification_document",
    "verification": "account_ownership_verification",
    "account": "checking_account_creation",
    "card": "card_issuing_virtual",
    "webhook": "webhook_notifications",
    "dispute": "dispute_management",
    "balance": "account_balance_check",
    "transaction": "transaction_history",
    "mandate": "sepa_direct_debit",
    "setup_intent": "recurring_billing",
    "price": "subscription_management",
    "coupon": "subscription_management",
    "tax": "tax_calculation",
}


class OpenAPIParserTool:
    """Parse OpenAPI specs to extract high-confidence data."""

    def run(self, spec_text: str) -> dict:
        try:
            spec = json.loads(spec_text)
        except json.JSONDecodeError:
            try:
                import yaml
                spec = yaml.safe_load(spec_text)
            except Exception:
                return {}

        result = {
            "endpoints_count": 0,
            "capabilities_from_paths": [],
            "auth_methods": [],
            "api_version": None,
        }

        info = spec.get("info", {})
        result["api_version"] = info.get("version")

        # Auth
        schemes = (
            spec.get("components", {}).get("securitySchemes", {})
            or spec.get("securityDefinitions", {})
        )
        for name, scheme in schemes.items():
            result["auth_methods"].append({
                "name": name,
                "type": scheme.get("type"),
            })

        # Paths → capabilities
        paths = spec.get("paths", {})
        result["endpoints_count"] = len(paths)

        found = set()
        for path in paths:
            for keyword, cap in CAPABILITY_MAP.items():
                if keyword in path.lower():
                    found.add(cap)

        result["capabilities_from_paths"] = sorted(found)
        return result
