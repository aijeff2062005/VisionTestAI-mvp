"""Local DMN decision-table engine (stdlib XML — no Kogito required).

Parses DMN 1.3 decision tables with simple FEEL literals:
  - strings in quotes
  - numbers / booleans
  - comparisons: >=, >, <=, <, =
  - empty cell = any
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ac.models import ActionName, DecisionResult

logger = logging.getLogger(__name__)

NS = {
    "dmn": "https://www.omg.org/spec/DMN/20191111/MODEL/",
}


@dataclass
class InputClause:
    id: str
    label: str
    expression: str  # fact key


@dataclass
class OutputClause:
    id: str
    name: str


@dataclass
class Rule:
    input_entries: list[str]
    output_entries: dict[str, str]


@dataclass
class DecisionTable:
    name: str
    hit_policy: str
    inputs: list[InputClause] = field(default_factory=list)
    outputs: list[OutputClause] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _find(el: ET.Element, path: str) -> ET.Element | None:
    return el.find(path, NS)


def _findall(el: ET.Element, path: str) -> list[ET.Element]:
    return list(el.findall(path, NS))


def parse_dmn(path: Path) -> dict[str, DecisionTable]:
    tree = ET.parse(path)
    root = tree.getroot()
    tables: dict[str, DecisionTable] = {}
    for decision in _findall(root, "dmn:decision"):
        name = decision.get("name") or decision.get("id") or "decision"
        dt_el = _find(decision, "dmn:decisionTable")
        if dt_el is None:
            continue
        hit = dt_el.get("hitPolicy") or "FIRST"
        inputs: list[InputClause] = []
        for inp in _findall(dt_el, "dmn:input"):
            label = inp.get("label") or ""
            expr_el = _find(inp, "dmn:inputExpression")
            text_el = _find(expr_el, "dmn:text") if expr_el is not None else None
            expr = _text(text_el) or label
            inputs.append(InputClause(id=inp.get("id") or label, label=label, expression=expr))
        outputs: list[OutputClause] = []
        for out in _findall(dt_el, "dmn:output"):
            outputs.append(OutputClause(id=out.get("id") or "", name=out.get("name") or out.get("label") or ""))
        rules: list[Rule] = []
        for rule_el in _findall(dt_el, "dmn:rule"):
            in_entries = [_text(_find(e, "dmn:text")) for e in _findall(rule_el, "dmn:inputEntry")]
            out_map: dict[str, str] = {}
            out_els = _findall(rule_el, "dmn:outputEntry")
            for i, oe in enumerate(out_els):
                key = outputs[i].name if i < len(outputs) else f"out{i}"
                out_map[key] = _text(_find(oe, "dmn:text"))
            rules.append(Rule(input_entries=in_entries, output_entries=out_map))
        tables[name] = DecisionTable(name=name, hit_policy=hit, inputs=inputs, outputs=outputs, rules=rules)
    return tables


_CMP = re.compile(r"^\s*(>=|<=|>|<|=)\s*(.+)\s*$")


def _parse_literal(raw: str) -> Any:
    s = raw.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _match_entry(entry: str, value: Any) -> bool:
    entry = (entry or "").strip()
    if entry in ("", "-", "null", "any"):
        return True
    # list of alternatives: "a", "b"
    if "," in entry and not entry.strip().startswith((">=", "<=", ">", "<", "=")):
        parts = [p.strip() for p in entry.split(",")]
        return any(_match_entry(p, value) for p in parts)
    m = _CMP.match(entry)
    if m:
        op, rhs_raw = m.group(1), m.group(2)
        rhs = _parse_literal(rhs_raw)
        try:
            if op == ">=":
                return value >= rhs
            if op == "<=":
                return value <= rhs
            if op == ">":
                return value > rhs
            if op == "<":
                return value < rhs
            if op == "=":
                return value == rhs
        except TypeError:
            return False
    expected = _parse_literal(entry)
    return value == expected


def evaluate_table(table: DecisionTable, facts: dict[str, Any]) -> dict[str, Any] | None:
    for rule in table.rules:
        ok = True
        for i, clause in enumerate(table.inputs):
            entry = rule.input_entries[i] if i < len(rule.input_entries) else ""
            fact_val = facts.get(clause.expression)
            if not _match_entry(entry, fact_val):
                ok = False
                break
        if ok:
            out: dict[str, Any] = {}
            for k, v in rule.output_entries.items():
                out[k] = _parse_literal(v) if v not in ("",) else None
            return out
        if table.hit_policy.upper() == "FIRST":
            continue
    return None


class DmnEngine:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tables = parse_dmn(path)
        logger.info("Loaded DMN tables from %s: %s", path, list(self.tables))

    def decide_next_action(self, facts: dict[str, Any]) -> DecisionResult:
        table = self.tables.get("NextAction")
        if table is None:
            # fallback: first table
            table = next(iter(self.tables.values()))
        raw = evaluate_table(table, facts) or {"action": "IDLE", "step_id": "idle"}
        action_str = str(raw.get("action") or "IDLE")
        try:
            action = ActionName(action_str)
        except ValueError:
            action = ActionName.IDLE
        step_id = raw.get("step_id")
        params = {k: v for k, v in raw.items() if k not in ("action", "step_id")}
        return DecisionResult(action=action, step_id=str(step_id) if step_id else None, params=params)
