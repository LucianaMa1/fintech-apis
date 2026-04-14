"""
Validator Tool — Reconcile and validate extracted data.
"""

import logging

log = logging.getLogger("tool.validate")


class ValidatorTool:
    """
    Validates and reconciles data from LLM extraction,
    OpenAPI specs, and existing seed data.

    Priority: OpenAPI spec > LLM extraction > existing seed data
    Multi-source confirmation boosts confidence.
    """

    def run(
        self,
        extracted: dict,
        openapi_data: dict,
        existing: dict,
    ) -> dict:
        """
        Returns dict of field_name -> {value, confidence, method, evidence}
        """
        validated = {}

        # ── Capabilities ──
        caps_llm = set(extracted.get("capabilities", {}).get("values") or [])
        caps_spec = set(openapi_data.get("capabilities_from_paths", []))
        caps_existing = set(existing.get("capabilities", []))

        all_caps = caps_llm | caps_spec | caps_existing
        if all_caps:
            # Score each capability by how many sources confirm it
            scored = {}
            for cap in all_caps:
                sources = sum([cap in caps_llm, cap in caps_spec, cap in caps_existing])
                scored[cap] = min(1.0, 0.4 + sources * 0.2)

            avg_conf = sum(scored.values()) / len(scored)
            methods = []
            if caps_llm: methods.append("llm")
            if caps_spec: methods.append("openapi")
            if caps_existing: methods.append("seed")

            validated["capabilities"] = {
                "value": sorted(all_caps),
                "confidence": round(avg_conf, 2),
                "method": "+".join(methods),
                "evidence": extracted.get("capabilities", {}).get("evidence", ""),
            }

        # ── List fields ──
        for field in [
            "supported_currencies", "sdks", "api_spec_format",
            "supported_payment_rails", "compliance_certifications",
        ]:
            llm_data = extracted.get(field, {})
            llm_vals = llm_data.get("values")
            llm_conf = llm_data.get("confidence", 0)
            existing_vals = existing.get(field)

            if llm_vals and llm_conf >= 0.5:
                validated[field] = {
                    "value": llm_vals,
                    "confidence": round(llm_conf, 2),
                    "method": "llm",
                    "evidence": llm_data.get("evidence", ""),
                }
            elif existing_vals:
                validated[field] = {
                    "value": existing_vals,
                    "confidence": 0.4,
                    "method": "seed",
                    "evidence": "kept from seed — llm extraction insufficient",
                }

        # ── Pricing ──
        pricing_llm = extracted.get("pricing_indicative", {})
        pricing_existing = existing.get("pricing_indicative")

        if pricing_llm.get("confidence", 0) >= 0.4:
            validated["pricing_indicative"] = {
                "value": pricing_llm.get("values", {}),
                "confidence": round(pricing_llm.get("confidence", 0), 2),
                "method": "llm",
                "evidence": pricing_llm.get("evidence", ""),
            }
        elif pricing_existing:
            validated["pricing_indicative"] = {
                "value": pricing_existing,
                "confidence": 0.3,
                "method": "seed",
                "evidence": "kept from seed — not verified",
            }

        return validated
