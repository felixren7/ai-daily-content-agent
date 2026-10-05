"""Deterministic offline provider for local evaluation and dry runs."""

from __future__ import annotations

import json
import re

from app.llm.base import LLMProvider, LLMResponse


class TemplateProvider(LLMProvider):
    provider_name = "template"
    model = "grounded-template-v1"

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> LLMResponse:
        match = re.search(r"BEGIN_JSON\s*(\{.*\})\s*END_JSON", user_prompt, re.DOTALL)
        if not match:
            raise RuntimeError("Template provider received no structured source data")
        payload = json.loads(match.group(1))
        mode = payload["mode"]
        title = payload["title"]
        summary = payload.get("summary") or ""
        facts = [claim["text"] for claim in payload.get("claims", []) if claim.get("supported")]
        sources = payload.get("sources", [])
        if mode == "news":
            fact_lines = "\n".join(f"- {fact}" for fact in facts[:4])
            technical_details = (
                fact_lines or "- The primary source did not provide enough technical detail."
            )
            source_lines = "\n".join(
                f"- {item['title']}: {item['url']}" for item in sources if item.get("url")
            )
            content = (
                f"{title}\n\n"
                "What happened?\n"
                f"{summary or (facts[0] if facts else title)}\n\n"
                "Why it matters\n"
                "The practical significance depends on the reported capability, availability, and "
                "measured evidence—not the announcement language alone.\n\n"
                "Technical details\n"
                f"{technical_details}\n\n"
                "Takeaway\n"
                "Treat the source claims as the current evidence boundary and verify independent "
                "benchmarks before making deployment decisions.\n\n"
                f"Sources\n{source_lines}"
            )
        else:
            source_lines = "\n".join(
                f"- {item['title']}: {item['url']}" for item in sources if item.get("url")
            )
            content = (
                f"{title}\n\n"
                f"One-sentence explanation\n{summary}\n\n"
                "How it works\n"
                f"{facts[0] if facts else summary}\n\n"
                "Simple example\n"
                f"A team uses {title} in a bounded workflow, measures the output, and keeps a "
                "human review step for high-impact decisions.\n\n"
                "Why it matters\n"
                "It provides a concrete design tool, but its value depends on data quality, "
                "evaluation, and operational constraints.\n\n"
                "Real-world application\n"
                "Use it where the mechanism matches a measurable product or engineering need.\n\n"
                "Key takeaway\n"
                "Understand the mechanism before choosing the tool.\n\n"
                f"Sources\n{source_lines}"
            )
        response = json.dumps(
            {"title": title, "summary": summary or title, "content": content},
            ensure_ascii=False,
        )
        return LLMResponse(
            text=response,
            provider=self.provider_name,
            model=self.model,
            metadata={"offline": True, "deterministic": True},
        )
