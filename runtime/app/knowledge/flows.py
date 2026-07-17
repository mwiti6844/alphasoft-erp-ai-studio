from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "why",
}

PROCESS_PATTERNS = (
    "how do i",
    "how can i",
    "why can't",
    "why cant",
    "why can’t",
    "why do i",
    "what does",
    "what is",
    "where do i",
    "set up",
    "setup",
    "configure",
    "create",
    "add",
    "access denied",
)


@dataclass(frozen=True)
class FlowStep:
    screen: str
    action: str
    route: str | None = None


@dataclass(frozen=True)
class FlowResource:
    id: str
    version: int
    module: str
    title: str
    audience: str
    summary: str
    prerequisites: tuple[str, ...]
    permissions: tuple[str, ...]
    steps: tuple[FlowStep, ...]
    related_ai_tools: tuple[str, ...]
    related_flows: tuple[str, ...]
    common_questions: tuple[str, ...]
    common_errors: tuple[dict[str, str], ...]
    notes: str

    @property
    def search_text(self) -> str:
        errors = " ".join(
            " ".join(str(value) for value in error.values()) for error in self.common_errors
        )
        return " ".join(
            [
                self.id,
                self.module,
                self.title,
                self.summary,
                " ".join(self.prerequisites),
                " ".join(self.permissions),
                " ".join(self.common_questions),
                errors,
                self.notes,
            ]
        )

    def prompt_block(self) -> str:
        lines = [
            f"Source: {self.id} v{self.version} — {self.title}",
            f"Summary: {self.summary.strip()}",
        ]
        if self.prerequisites:
            lines.append("Prerequisites: " + "; ".join(self.prerequisites[:4]))
        if self.permissions:
            lines.append("Permissions: " + ", ".join(self.permissions[:4]))
        lines.append("Steps:")
        for index, step in enumerate(self.steps[:6], start=1):
            route = f" ({step.route})" if step.route else ""
            lines.append(f"{index}. {step.screen}{route}: {step.action}")
        if self.common_errors:
            lines.append("Common issues:")
            for error in self.common_errors[:3]:
                symptom = error.get("symptom", "")
                cause = error.get("cause", "")
                resolution = error.get("resolution", "")
                lines.append(f"- {symptom}: {cause} Resolution: {resolution}")
        if self.notes:
            lines.append(f"Notes: {self.notes.strip()}")
        return "\n".join(lines)

    def citation(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "title": self.title}


@dataclass(frozen=True)
class FlowMatch:
    resource: FlowResource
    score: int


def is_process_question(message: str) -> bool:
    normalized = normalize_text(message)
    if any(pattern in normalized for pattern in PROCESS_PATTERNS):
        return True
    return normalized.endswith("?") and any(
        token in normalized for token in ("setup", "configure", "permission", "access", "screen")
    )


def retrieve_flows(message: str, module_scope: str, limit: int = 3) -> tuple[FlowMatch, ...]:
    if not is_process_question(message):
        return ()

    query_tokens = tokens(message)
    if not query_tokens:
        return ()

    matches: list[FlowMatch] = []
    for resource in load_flow_resources():
        score = score_resource(resource, query_tokens, module_scope, message)
        if score >= 3:
            matches.append(FlowMatch(resource=resource, score=score))

    matches.sort(key=lambda match: (-match.score, match.resource.id))
    return tuple(matches[:limit])


def flow_context_prompt(matches: tuple[FlowMatch, ...]) -> str:
    if not matches:
        return (
            "\nProduct-flow knowledge: no curated flow resource matched this process question. "
            "If the user is asking how AlphaSoft works, say the flow is not documented yet and "
            "offer a narrower question or a live data lookup you can support.\n"
        )

    blocks = "\n\n".join(match.resource.prompt_block() for match in matches)
    return (
        "\nProduct-flow knowledge matched this question. Use only these sources for process "
        "steps, mention prerequisites or permissions when relevant, and do not invent screens. "
        "End the answer naturally; citations will be rendered separately.\n"
        f"{blocks}\n"
    )


@lru_cache(maxsize=1)
def load_flow_resources() -> tuple[FlowResource, ...]:
    flow_dir = find_flow_dir()
    resources = []
    for path in sorted(flow_dir.glob("*/*.yaml")):
        data = yaml.safe_load(path.read_text())
        if isinstance(data, dict):
            resources.append(parse_flow_resource(data))
    return tuple(resources)


def find_flow_dir() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[3] / "contracts" / "flows",
        current.parents[2] / "contracts" / "flows",
        Path("/app/contracts/flows"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Flow knowledge resources are not available.")


def parse_flow_resource(data: dict[str, Any]) -> FlowResource:
    return FlowResource(
        id=str(data["id"]),
        version=int(data.get("version", 1)),
        module=str(data["module"]),
        title=str(data["title"]),
        audience=str(data.get("audience", "tenant_user")),
        summary=str(data.get("summary", "")),
        prerequisites=tuple(str(item) for item in data.get("prerequisites", [])),
        permissions=tuple(str(item) for item in data.get("permissions", [])),
        steps=tuple(parse_step(step) for step in data.get("steps", [])),
        related_ai_tools=tuple(str(item) for item in data.get("related_ai_tools", [])),
        related_flows=tuple(str(item) for item in data.get("related_flows", [])),
        common_questions=tuple(str(item) for item in data.get("common_questions", [])),
        common_errors=tuple(
            {
                "symptom": str(item.get("symptom", "")),
                "cause": str(item.get("cause", "")),
                "resolution": str(item.get("resolution", "")),
            }
            for item in data.get("common_errors", [])
            if isinstance(item, dict)
        ),
        notes=str(data.get("notes", "")),
    )


def parse_step(data: dict[str, Any]) -> FlowStep:
    return FlowStep(
        screen=str(data.get("screen", "")),
        route=str(data["route"]) if data.get("route") else None,
        action=str(data.get("action", "")),
    )


def score_resource(
    resource: FlowResource, query_tokens: set[str], module_scope: str, message: str
) -> int:
    resource_tokens = tokens(resource.search_text)
    overlap = query_tokens & resource_tokens
    score = len(overlap)

    normalized = normalize_text(message)
    for question in resource.common_questions:
        question_text = normalize_text(question)
        if question_text and (question_text in normalized or normalized in question_text):
            score += 8

    if resource.module == module_scope:
        score += 2
    if module_scope in resource.related_flows or module_scope in resource.related_ai_tools:
        score += 1
    if resource.module in {"permissions", "taxes"}:
        score += 1
    if resource.module == "permissions" and any(
        phrase in normalized for phrase in ("can't", "cant", "can’t", "access", "permission", "denied")
    ):
        score += 8
    return score


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(text))
        if len(token) > 2 and token not in STOP_WORDS
    }


def normalize_text(text: str) -> str:
    return text.lower().replace("’", "'").strip()
