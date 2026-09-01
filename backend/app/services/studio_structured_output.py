"""Deterministic JSON hardening for model output (brief section 6.4).

Order: strict parse -> unique code block / unique JSON object extraction ->
safe bounded format fixes (trailing commas, known field aliases) -> raise if
still ambiguous. Only deterministic, reversible repairs are applied here;
anything else must go through the one-time schema-repair model call or be
reported to the deterministic fallback, never silently accepted.
"""
from __future__ import annotations

import json
import re

# Contract field -> accepted model aliases, scoped per container so a generic key
# like "id" or "title" can never leak into the wrong field. Aliases are only copied
# when the target field is missing entirely; existing values are never overwritten.
SCENE_ALIASES = {"scene_id": ("id", "sceneNumber"), "narration": ("subtitle", "narration_text"),
                 "heading": ("headline", "title"), "visual_action": ("visual", "action")}
CLAIM_ALIASES = {"claim_id": ("id",), "source_id": ("source",)}
SCENE_MARKERS = {"scene_id", "narration", "visual_action", "role", "claim_ids",
                 "narration_text", "subtitle", "visual", "sceneNumber", "headline"}
CLAIM_MARKERS = {"claim_id", "quote", "boundary", "source_id", "evidence"}

FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")
TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _locate_object(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    return start, end


def _brace_scan(candidate):
    """Return the number of complete top-level objects in the span, ignoring strings."""
    depth, objects, in_string, escaped = 0, 0, False, False
    for char in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                objects += 1
    return objects


def extract_json_object(text):
    """Accept a JSON code block or the unique JSON object in the body; reject ambiguity."""
    text = (text or "").strip()
    if not text:
        raise ValueError("模型没有返回内容")
    fences = FENCE.findall(text)
    if len(fences) > 1:
        raise ValueError("模型返回了多个JSON代码块，无法确定唯一结果")
    if fences:
        return fences[0].strip()
    location = _locate_object(text)
    if location is None:
        raise ValueError("返回内容中没有JSON对象")
    start, end = location
    candidate = text[start:end + 1]
    if _brace_scan(candidate) > 1:
        raise ValueError("返回正文包含多个JSON对象，无法确定唯一结果")
    remainder = text[:start] + text[end + 1:]
    if _locate_object(remainder):
        raise ValueError("返回正文包含多个JSON对象，无法确定唯一结果")
    return candidate


def safe_fix_json(text):
    """Only trailing commas; all other malformations must go through a repair call."""
    return TRAILING_COMMA.sub(r"\1", text)


def repair_known_aliases(data):
    """Copy scoped aliases into contract field names when the field is missing."""
    changed = []
    if isinstance(data, list):
        for item in data:
            changed.extend(repair_known_aliases(item))
    elif isinstance(data, dict):
        if any(key in data for key in SCENE_MARKERS):
            rules = SCENE_ALIASES
        elif any(key in data for key in CLAIM_MARKERS):
            rules = CLAIM_ALIASES
        else:
            rules = {}
        for field, aliases in rules.items():
            if field not in data:
                for alias in aliases:
                    if alias in data:
                        data[field] = data[alias]
                        changed.append({"field": field, "alias": alias})
                        break
        for value in data.values():
            if isinstance(value, (dict, list)):
                changed.extend(repair_known_aliases(value))
    return changed


def hardened_json(content):
    """Full hardening pipeline; returns (object, hardening_note) or raises ValueError."""
    raw = extract_json_object(content)
    fixed = safe_fix_json(raw)
    if fixed != raw:
        raw = fixed
        note = "trailing_comma_fixed"
    elif FENCE.search(content or ""):
        note = "code_block"
    elif raw != (content or "").strip():
        note = "embedded_object"
    else:
        note = "plain"
    data = json.loads(raw)
    aliases = repair_known_aliases(data)
    if aliases:
        note += ";alias_fixed:" + ",".join(entry["field"] for entry in aliases)
    return data, note
