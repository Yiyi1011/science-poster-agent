from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
EVAL_ROOT = WORKSPACE_ROOT / "retrieval-evaluation"
DATASET_PATH = EVAL_ROOT / "retrieval-tests-v1.jsonl"
RESULTS_PATH = EVAL_ROOT / "retrieval-results-v1.json"
REPORT_PATH = EVAL_ROOT / "retrieval-report-v1.md"
CHECKPOINT_PATH = EVAL_ROOT / "retrieval-results-checkpoint-v1.json"
LOCAL_API_URL = "http://127.0.0.1:8000/api/knowledge/query"

sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.models import KnowledgeAnswer  # noqa: E402


def load_tests() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def source_ids_in_reference(reference: Any, expected: list[str]) -> set[str]:
    haystack = "\n".join(
        [reference.title, reference.doc_name, reference.doc_id, reference.text]
    )
    return {source_id for source_id in expected if source_id in haystack}


async def query_with_retry(client: httpx.AsyncClient, question: str) -> KnowledgeAnswer:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = await client.post(LOCAL_API_URL, json={"question": question})
            response.raise_for_status()
            return KnowledgeAnswer.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < 4:
                await asyncio.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"retrieval failed after 4 attempts: {type(last_error).__name__}") from last_error


async def evaluate_one(client: httpx.AsyncClient, case: dict[str, Any]) -> dict[str, Any]:
    answer = await query_with_retry(client, case["question"])
    expected = case["expected_source_ids"]
    matched: set[str] = set()
    for reference in answer.references:
        matched.update(source_ids_in_reference(reference, expected))

    expects_evidence = bool(expected)
    threshold_passed = answer.status == "supported"
    source_hit = bool(matched) if expects_evidence else None
    passed = (threshold_passed and bool(source_hit)) if expects_evidence else not threshold_passed
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answer_policy": case["answer_policy"],
        "expected_source_ids": expected,
        "matched_source_ids": sorted(matched),
        "status": answer.status,
        "max_score": answer.max_retrieval_score,
        "threshold": answer.threshold,
        "source_hit": source_hit,
        "passed": passed,
        "top_document": answer.references[0].doc_name if answer.references else "",
        "returned_documents": list(
            dict.fromkeys(ref.doc_name for ref in answer.references if ref.doc_name)
        ),
        "request_id": answer.request_id,
    }


def threshold_table(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        tp = tn = fp = fn = 0
        for item in results:
            actual_positive = bool(item["expected_source_ids"])
            predicted_positive = (item["max_score"] or 0) >= threshold
            if actual_positive and predicted_positive:
                tp += 1
            elif actual_positive:
                fn += 1
            elif predicted_positive:
                fp += 1
            else:
                tn += 1
        rows.append(
            {
                "threshold": threshold,
                "tp": tp,
                "tn": tn,
                "fp": fp,
                "fn": fn,
                "accuracy": round((tp + tn) / len(results), 4),
            }
        )
    return rows


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# 百炼知识库30条固定检索评测 v1",
        "",
        f"- 执行时间：{payload['recorded_at']}",
        f"- 地域：`{payload['region']}`",
        f"- 检索阈值：`{payload['threshold']:.2f}`",
        f"- 总测试：{summary['total']}",
        f"- 严格通过：{summary['passed']}（{summary['pass_rate']:.1%}）",
        f"- 有期望来源问题的Top5来源命中率：{summary['source_hit_rate']:.1%}",
        f"- 低于阈值拒答：{summary['refused']}条",
        "",
        "## 明细",
        "",
        "| ID | 类别 | 最高分 | 状态 | 期望来源命中 | Top 1文档 | 严格判定 |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in payload["results"]:
        hit = "—" if item["source_hit"] is None else ("是" if item["source_hit"] else "否")
        lines.append(
            f"| {item['id']} | {item['category']} | {(item['max_score'] or 0):.3f} | "
            f"{item['status']} | {hit} | {item['top_document']} | {'通过' if item['passed'] else '需复核'} |"
        )

    lines.extend(
        [
            "",
            "## 阈值扫描",
            "",
            "该表仅把“是否配置期望来源”视为正负类，用于观察阈值变化；语义拒答仍需规则或生成模型判断。",
            "",
            "| 阈值 | TP | TN | FP | FN | 准确率 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["threshold_scan"]:
        lines.append(
            f"| {row['threshold']:.2f} | {row['tp']} | {row['tn']} | {row['fp']} | {row['fn']} | {row['accuracy']:.1%} |"
        )

    failed = [item for item in payload["results"] if not item["passed"]]
    lines.extend(["", "## 需复核项目", ""])
    if not failed:
        lines.append("无。")
    for item in failed:
        lines.append(
            f"- `{item['id']}`：{item['question']}；最高分{(item['max_score'] or 0):.3f}，"
            f"状态`{item['status']}`，匹配来源{item['matched_source_ids'] or '无'}。"
        )

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本报告不保存API Key、Authorization请求头或检索正文。",
            "- request_id仅保存在JSON结果中，用于账单与问题追踪。",
            "- 检索命中不等于最终答案正确；生成阶段仍需事实卡、条件边界和人工/多模态审核。",
            "",
        ]
    )
    return "\n".join(lines)


async def main() -> None:
    tests = load_tests()
    results: list[dict[str, Any]] = []
    if CHECKPOINT_PATH.exists():
        checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        results = checkpoint.get("results", [])
        print(f"RESUME={len(results)}", flush=True)
    completed_ids = {item["id"] for item in results}

    async with httpx.AsyncClient(timeout=180) as client:
        for index, case in enumerate(tests, start=1):
            if case["id"] in completed_ids:
                continue
            result = await evaluate_one(client, case)
            results.append(result)
            CHECKPOINT_PATH.write_text(
                json.dumps({"results": results}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                f"[{index:02d}/{len(tests)}] {result['id']} "
                f"status={result['status']} score={(result['max_score'] or 0):.3f} "
                f"source_hit={result['source_hit']}",
                flush=True,
            )

    results.sort(key=lambda item: item["id"])

    positive = [item for item in results if item["expected_source_ids"]]
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "pass_rate": sum(1 for item in results if item["passed"]) / len(results),
        "source_hit_rate": sum(1 for item in positive if item["source_hit"]) / len(positive),
        "refused": sum(1 for item in results if item["status"] == "insufficient_evidence"),
    }
    payload = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "region": settings.region,
        "threshold": settings.retrieval_min_score,
        "secret_recorded": False,
        "summary": summary,
        "threshold_scan": threshold_table(results),
        "results": results,
    }
    RESULTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    REPORT_PATH.write_text(markdown_report(payload), encoding="utf-8")
    print(f"RESULTS={RESULTS_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
