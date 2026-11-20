"""模型评估结果数据集：汇入样本结果、混淆计数、分组命中率、覆盖缺口与版本比较。

口径约定（发布评审以此为准，看板与接口返回同一份说明）：

- 主比较：共同覆盖准确率。只统计两个版本都给出预测的样本，
  准确率 = 共同覆盖内正确数 / 共同覆盖样本数；共同覆盖为 0 时不给出差值。
- 辅助比较：全评估集正确响应占比。正确数 / 评估集样本总数，
  模型弃答计入分母但不计为正确，避免「少答少错」把覆盖率差距藏起来。
- 差值方向：版本 A - 版本 B。
- 少数类别：真实分类在评估集中占比低于 30% 的类别；少数类别上的弃答单独列出。
- 人工复核：弃答样本与金标「人工复核」样本单独成清单，复核结论回写到结果行。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE_BATCH = "model_eval_batch"
MODULE_SAMPLE = "model_eval_sample"
MODULE_RESULT = "model_eval_result"
MODULE_COMPARISON = "model_eval_comparison"
MODEL_MODULE = "model"

MINORITY_THRESHOLD = 0.30
REVIEW_TRUTH_CLASS = "人工复核"
ABSTAIN_LABEL = "弃答"
ANSWERED_LABEL = "已作答"

PRIMARY_METRIC = "共同覆盖准确率"
PRIMARY_DEFINITION = (
    "只取两个版本都给出预测的样本，准确率 = 共同覆盖内正确数 / 共同覆盖样本数；"
    "共同覆盖为 0 个样本时不给出差值。"
)
SECONDARY_METRIC = "全评估集正确响应占比"
SECONDARY_DEFINITION = (
    "正确数 / 评估集样本总数；模型弃答计入分母但不计为正确，"
    "用于回答「实际有多少样本得到了正确答复」。"
)


class EvalError(ValueError):
    """汇入或比较时可以直接展示给使用者的业务错误。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _sort_ids(ids: set[str]) -> list[str]:
    return sorted(ids, key=lambda value: str(value))


def _batch_by_code(code: str) -> dict[str, Any] | None:
    for row in store.rows(MODULE_BATCH):
        if str(row.get("批次编号")) == code:
            return row
    return None


def _resolve_batch(batch_id: int | None, batch_code: str | None = None) -> dict[str, Any]:
    batch = None
    if batch_id is not None:
        batch = store.find(MODULE_BATCH, batch_id)
    elif batch_code:
        batch = _batch_by_code(batch_code)
    if batch is None:
        raise EvalError(f"评估批次 {batch_code or batch_id} 不存在")
    return batch


def _samples_of(batch_id: int) -> list[dict[str, Any]]:
    return [row for row in store.rows(MODULE_SAMPLE) if int(row.get("批次ID", 0)) == batch_id]


def _results_of(batch_id: int, model: str | None = None, version: str | None = None) -> list[dict[str, Any]]:
    rows = [row for row in store.rows(MODULE_RESULT) if int(row.get("批次ID", 0)) == batch_id]
    if model is not None:
        rows = [row for row in rows if str(row.get("模型编号")) == model]
    if version is not None:
        rows = [row for row in rows if str(row.get("模型版本")) == version]
    return rows


def _class_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        label = str(sample.get("真实分类") or "")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _minority_classes(samples: list[dict[str, Any]]) -> set[str]:
    total = len(samples)
    if total == 0:
        return set()
    return {
        label for label, count in _class_counts(samples).items()
        if count / total < MINORITY_THRESHOLD
    }


def _review_reasons(truth: str, prediction: str, minority: set[str]) -> str:
    reasons: list[str] = []
    if not prediction:
        reasons.append("少数类别弃答（模型未给出预测）" if truth in minority else "模型弃答")
    if truth == REVIEW_TRUTH_CLASS:
        reasons.append("金标为人工复核")
    return "；".join(reasons)


def _is_answered(row: dict[str, Any] | None) -> bool:
    return bool(row) and row.get("预测状态") == ANSWERED_LABEL


def _is_correct(row: dict[str, Any] | None) -> bool:
    return (
        _is_answered(row)
        and str(row.get("预测分类")) == str(row.get("真实分类"))
    )


def _metrics_explain(batch: dict[str, Any], model: str, version: str) -> dict[str, Any]:
    return {
        "评估批次": batch.get("批次编号"),
        "评估集编号": batch.get("评估集编号"),
        "评估集名称": batch.get("评估集名称"),
        "模型编号": model,
        "模型版本": version,
        "口径说明": {
            "命中率": "正确数 / 已作答样本数，回答「答了的里面有多少对」",
            "覆盖率": "已作答样本数 / 评估集样本总数，回答「实际答了多少」",
            "正确响应占比": "正确数 / 评估集样本总数，弃答计入分母且不算正确",
            "分组命中率": "分组内正确数 / 分组内已作答样本数，分母不含弃答",
        },
    }


class ModelEvalService:
    # ---------- 评估批次、样本与口径 ----------

    def metric_definitions(self) -> dict[str, Any]:
        return {
            "主比较": PRIMARY_METRIC,
            "主比较定义": PRIMARY_DEFINITION,
            "辅助比较": SECONDARY_METRIC,
            "辅助比较定义": SECONDARY_DEFINITION,
            "差值方向": "版本A - 版本B",
            "少数类别阈值": f"真实分类样本占比低于 {MINORITY_THRESHOLD:.0%} 视为少数类别",
            "弃答处理": "预测分类为空即弃答；弃答计入覆盖率分母，但不计为正确预测",
            "人工复核": "弃答样本与金标「人工复核」样本单独列出，复核结论回写结果行",
        }

    def list_batches(self) -> list[dict[str, Any]]:
        batches = []
        for batch in store.rows(MODULE_BATCH):
            batch_id = int(batch["id"])
            samples = _samples_of(batch_id)
            versions = {(str(row.get("模型编号")), str(row.get("模型版本"))) for row in _results_of(batch_id)}
            batches.append({
                **batch,
                "样本总数": len(samples) or int(batch.get("样本总数") or 0),
                "已汇入版本数": len(versions),
            })
        return batches

    def get_batch(self, batch_id: int) -> dict[str, Any]:
        batch = _resolve_batch(batch_id)
        samples = _samples_of(batch_id)
        return {
            **batch,
            "样本": samples,
            "真实分类分布": _class_counts(samples),
            "少数类别": sorted(_minority_classes(samples)),
            "口径说明": self.metric_definitions(),
        }

    def list_samples(self, batch_id: int) -> list[dict[str, Any]]:
        _resolve_batch(batch_id)
        return _samples_of(batch_id)

    # ---------- 结果汇入 ----------

    def import_results(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        batch_code = str(values.get("评估批次") or values.get("批次编号") or "").strip()
        batch = _batch_by_code(batch_code)
        if batch is None:
            return None, f"评估批次 {batch_code or '（未填写）'} 不存在"
        batch_id = int(batch["id"])

        model = str(values.get("模型编号") or "").strip()
        version = str(values.get("模型版本") or "").strip()
        if not model:
            return None, "缺少模型编号"
        if not version:
            return None, "缺少模型版本"
        if not any(str(row.get("模型编号")) == model for row in store.rows(MODEL_MODULE)):
            return None, f"模型 {model} 尚未登记，无法汇入评估结果"

        raw_results = values.get("results") or values.get("样本结果") or []
        if not isinstance(raw_results, list) or not raw_results:
            return None, "样本结果为空，请按样本编号逐条给出真实分类与预测分类"

        samples = _samples_of(batch_id)
        sample_index = {str(sample.get("样本编号")): sample for sample in samples}
        valid_classes = {str(sample.get("真实分类")) for sample in samples}
        minority = _minority_classes(samples)

        parsed: dict[str, dict[str, str]] = {}
        for position, raw in enumerate(raw_results, start=1):
            if not isinstance(raw, dict):
                return None, f"第 {position} 条结果不是对象，需要包含样本编号、真实分类、预测分类"
            sample_id = str(raw.get("样本编号") or "").strip()
            truth = str(raw.get("真实分类") or "").strip()
            prediction = str(raw.get("预测分类") or "").strip()
            if not sample_id:
                return None, f"第 {position} 条结果缺少样本编号"
            if sample_id not in sample_index:
                return None, f"样本 {sample_id} 不属于评估批次 {batch_code} 的评估集"
            if sample_id in parsed:
                return None, f"样本 {sample_id} 在本次汇入中重复出现"
            expected_truth = str(sample_index[sample_id].get("真实分类") or "")
            if truth != expected_truth:
                return None, f"样本 {sample_id} 的真实分类应为「{expected_truth}」，收到「{truth or '空'}」"
            if prediction and prediction not in valid_classes:
                return None, f"样本 {sample_id} 的预测分类「{prediction}」不在评估集分类范围内"
            parsed[sample_id] = {"truth": truth, "prediction": prediction, "group": str(sample_index[sample_id].get("样本分组") or "")}

        missing = [str(sample["样本编号"]) for sample in samples if str(sample["样本编号"]) not in parsed]
        if missing:
            return None, (
                f"评估集还有 {len(missing)} 个样本未汇入：{'、'.join(missing[:8])}"
                "；弃答样本也要登记一条空预测"
            )

        existing = _results_of(batch_id, model, version)
        overwrite = bool(values.get("覆盖已有"))
        if existing and not overwrite:
            return None, (
                f"{model} {version} 在批次 {batch_code} 已汇入 {len(existing)} 条结果；"
                "如需替换请勾选「覆盖已有」"
            )
        if existing:
            store._tables[MODULE_RESULT] = [
                row for row in store.rows(MODULE_RESULT)
                if not (
                    int(row.get("批次ID", 0)) == batch_id
                    and str(row.get("模型编号")) == model
                    and str(row.get("模型版本")) == version
                )
            ]

        result_rows = store.rows(MODULE_RESULT)
        next_id = max((int(row.get("id", 0)) for row in result_rows), default=0) + 1
        created: list[dict[str, Any]] = []
        for sample in samples:
            sample_id = str(sample["样本编号"])
            truth = str(sample.get("真实分类") or "")
            prediction = parsed[sample_id]["prediction"]
            reasons = _review_reasons(truth, prediction, minority)
            row = {
                "id": next_id,
                "status": "已入账",
                "pending": bool(reasons),
                "abnormal": False,
                "批次ID": batch_id,
                "评估批次": batch_code,
                "评估集编号": batch.get("评估集编号"),
                "模型编号": model,
                "模型版本": version,
                "样本编号": sample_id,
                "真实分类": truth,
                "预测分类": prediction,
                "预测状态": ANSWERED_LABEL if prediction else ABSTAIN_LABEL,
                "样本分组": sample.get("样本分组"),
                "人工复核": bool(reasons),
                "复核原因": reasons,
                "复核结论": "",
                "复核备注": "",
                "汇入时间": str(values.get("汇入时间") or _now()),
            }
            result_rows.append(row)
            created.append(row)
            next_id += 1

        answered = sum(1 for row in created if row["预测状态"] == ANSWERED_LABEL)
        review = sum(1 for row in created if row["人工复核"])
        message = (
            f"已汇入 {model} {version} 的 {len(created)} 条样本结果："
            f"作答 {answered} 条、弃答 {len(created) - answered} 条、待人工复核 {review} 条"
        )
        if existing:
            message += f"（已覆盖原有 {len(existing)} 条）"
        summary = {
            "批次": batch.get("批次编号"),
            "评估集编号": batch.get("评估集编号"),
            "模型编号": model,
            "模型版本": version,
            "样本总数": len(created),
            "已作答": answered,
            "弃答": len(created) - answered,
            "正确": sum(1 for row in created if _is_correct(row)),
            "待人工复核": review,
            "少数类别弃答": sum(
                1 for row in created
                if row["预测状态"] == ABSTAIN_LABEL and str(row["真实分类"]) in minority
            ),
        }
        return summary, message

    # ---------- 结果明细与人工复核 ----------

    def list_results(
        self,
        *,
        batch_id: int | None = None,
        model: str | None = None,
        version: str | None = None,
        prediction_status: str | None = None,
        group: str | None = None,
        review_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE_RESULT))
        if batch_id is not None:
            rows = [row for row in rows if int(row.get("批次ID", 0)) == batch_id]
        if model:
            rows = [row for row in rows if str(row.get("模型编号")) == model]
        if version:
            rows = [row for row in rows if str(row.get("模型版本")) == version]
        if prediction_status:
            rows = [row for row in rows if str(row.get("预测状态")) == prediction_status]
        if group:
            rows = [row for row in rows if str(row.get("样本分组")) == group]
        if review_only:
            rows = [row for row in rows if row.get("人工复核")]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def review_queue(self, batch_id: int | None = None) -> dict[str, Any]:
        rows, total = self.list_results(batch_id=batch_id, review_only=True, page=1, size=10000)
        minority: set[str] = set()
        if batch_id is not None:
            minority = _minority_classes(_samples_of(batch_id))
        summary = {
            "待复核总数": total,
            "弃答": sum(1 for row in rows if row.get("预测状态") == ABSTAIN_LABEL),
            "少数类别弃答": sum(
                1 for row in rows
                if row.get("预测状态") == ABSTAIN_LABEL and str(row.get("真实分类")) in minority
            ),
            "金标人工复核": sum(1 for row in rows if str(row.get("真实分类")) == REVIEW_TRUTH_CLASS),
            "已有复核结论": sum(1 for row in rows if row.get("复核结论")),
        }
        return {"summary": summary, "items": rows, "少数类别": sorted(minority)}

    def mark_reviewed(self, result_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE_RESULT, result_id)
        if row is None:
            return None, f"评估结果 {result_id} 不存在"
        if not row.get("人工复核"):
            return None, f"评估结果 {result_id} 当前不在人工复核清单里"
        conclusion = str(values.get("复核结论") or "").strip()
        if not conclusion:
            return None, "请填写复核结论后再登记"
        row["人工复核"] = False
        row["pending"] = False
        row["复核结论"] = conclusion
        row["复核备注"] = str(values.get("复核备注") or "").strip()
        return row, "人工复核结论已登记"

    # ---------- 版本指标 ----------

    def version_metrics(self, batch_id: int, model: str, version: str) -> dict[str, Any]:
        batch = _resolve_batch(batch_id)
        samples = _samples_of(batch_id)
        rows = _results_of(batch_id, model, version)
        if not rows:
            raise EvalError(f"{model} {version} 在批次 {batch.get('批次编号')} 没有评估结果")

        total = len(samples)
        answered = [row for row in rows if row.get("预测状态") == ANSWERED_LABEL]
        abstained = [row for row in rows if row.get("预测状态") == ABSTAIN_LABEL]
        correct = [row for row in answered if _is_correct(row)]
        wrong = [row for row in answered if not _is_correct(row)]
        minority = _minority_classes(samples)
        sample_group = {str(sample["样本编号"]): str(sample.get("样本分组") or "") for sample in samples}

        groups = []
        for name in sorted(set(sample_group.values())):
            group_ids = {sid for sid, group in sample_group.items() if group == name}
            group_rows = [row for row in rows if str(row.get("样本编号")) in group_ids]
            group_answered = [row for row in group_rows if row.get("预测状态") == ANSWERED_LABEL]
            group_correct = [row for row in group_answered if _is_correct(row)]
            group_abstained = [row for row in group_rows if row.get("预测状态") == ABSTAIN_LABEL]
            groups.append({
                "样本分组": name,
                "样本总数": len(group_ids),
                "已作答": len(group_answered),
                "弃答": len(group_abstained),
                "正确": len(group_correct),
                "错误": len(group_answered) - len(group_correct),
                "命中率": _ratio(len(group_correct), len(group_answered)),
                "覆盖率": _ratio(len(group_answered), len(group_ids)),
                "正确响应占比": _ratio(len(group_correct), len(group_ids)),
                "分组分母": {
                    "命中率": f"分组内已作答 {len(group_answered)} 个样本",
                    "正确响应占比": f"分组样本总数 {len(group_ids)} 个样本",
                },
                "少数类别弃答": [
                    str(row["样本编号"]) for row in group_abstained
                    if str(row["真实分类"]) in minority
                ],
            })

        confusion: dict[str, dict[str, int]] = {}
        for row in answered:
            truth = str(row.get("真实分类"))
            prediction = str(row.get("预测分类"))
            confusion.setdefault(truth, {})
            confusion[truth][prediction] = confusion[truth].get(prediction, 0) + 1

        return {
            **_metrics_explain(batch, model, version),
            "样本总数": total,
            "已作答": len(answered),
            "弃答": len(abstained),
            "正确": len(correct),
            "错误": len(wrong),
            "命中率": _ratio(len(correct), len(answered)),
            "覆盖率": _ratio(len(answered), total),
            "正确响应占比": _ratio(len(correct), total),
            "混淆计数": confusion,
            "混淆分母": f"已作答 {len(answered)} 个样本；弃答 {len(abstained)} 个样本不计入混淆矩阵",
            "分组": groups,
            "弃答样本": _sort_ids({str(row["样本编号"]) for row in abstained}),
            "少数类别弃答": [
                str(row["样本编号"]) for row in abstained
                if str(row["真实分类"]) in minority
            ],
            "少数类别": sorted(minority),
            "人工复核": sum(1 for row in rows if row.get("人工复核")),
        }

    def list_versions(self, batch_id: int) -> list[dict[str, Any]]:
        _resolve_batch(batch_id)
        versions = sorted({(str(row.get("模型编号")), str(row.get("模型版本"))) for row in _results_of(batch_id)})
        result = []
        for model, version in versions:
            metrics = self.version_metrics(batch_id, model, version)
            result.append({
                "模型编号": model,
                "模型版本": version,
                "样本总数": metrics["样本总数"],
                "已作答": metrics["已作答"],
                "弃答": metrics["弃答"],
                "正确": metrics["正确"],
                "覆盖率": metrics["覆盖率"],
                "正确响应占比": metrics["正确响应占比"],
                "命中率": metrics["命中率"],
                "人工复核": metrics["人工复核"],
            })
        return result

    def model_evaluations(self, model: str) -> list[dict[str, Any]]:
        """模型详情页用：该模型在各评估批次的版本指标与状态。"""
        entries = []
        for batch in store.rows(MODULE_BATCH):
            batch_id = int(batch["id"])
            versions = sorted({
                str(row.get("模型版本")) for row in _results_of(batch_id, model)
            })
            for version in versions:
                metrics = self.version_metrics(batch_id, model, version)
                entries.append({
                    "批次ID": batch_id,
                    "评估批次": batch.get("批次编号"),
                    "评估集编号": batch.get("评估集编号"),
                    "评估集名称": batch.get("评估集名称"),
                    "模型编号": model,
                    "模型版本": version,
                    "样本总数": metrics["样本总数"],
                    "已作答": metrics["已作答"],
                    "弃答": metrics["弃答"],
                    "正确": metrics["正确"],
                    "命中率": metrics["命中率"],
                    "覆盖率": metrics["覆盖率"],
                    "正确响应占比": metrics["正确响应占比"],
                    "少数类别弃答": metrics["少数类别弃答"],
                    "分组": metrics["分组"],
                    "混淆计数": metrics["混淆计数"],
                })
        return entries

    # ---------- 版本比较 ----------

    def compare(
        self,
        *,
        batch_id: int | None = None,
        batch_code: str | None = None,
        model_a: str,
        version_a: str,
        model_b: str,
        version_b: str,
        save: bool = True,
        note: str = "",
    ) -> dict[str, Any]:
        batch = _resolve_batch(batch_id, batch_code)
        batch_id = int(batch["id"])
        if (model_a, version_a) == (model_b, version_b):
            raise EvalError("两个比较对象是同一个模型版本，无法比较")

        rows_a = {str(row.get("样本编号")): row for row in _results_of(batch_id, model_a, version_a)}
        rows_b = {str(row.get("样本编号")): row for row in _results_of(batch_id, model_b, version_b)}
        if not rows_a:
            raise EvalError(f"{model_a} {version_a} 在批次 {batch.get('批次编号')} 没有评估结果")
        if not rows_b:
            raise EvalError(f"{model_b} {version_b} 在批次 {batch.get('批次编号')} 没有评估结果")

        samples = _samples_of(batch_id)
        sample_index = {str(sample["样本编号"]): sample for sample in samples}
        sample_group = {sid: str(sample.get("样本分组") or "") for sid, sample in sample_index.items()}
        total = len(samples)
        minority = _minority_classes(samples)

        answered_a = {sid for sid, row in rows_a.items() if _is_answered(row)}
        answered_b = {sid for sid, row in rows_b.items() if _is_answered(row)}
        common = sorted(answered_a & answered_b)
        only_a = sorted(answered_a - answered_b)
        only_b = sorted(answered_b - answered_a)
        both_abstained = sorted(set(rows_a) - answered_a - answered_b)

        correct_a_common = sum(1 for sid in common if _is_correct(rows_a.get(sid)))
        correct_b_common = sum(1 for sid in common if _is_correct(rows_b.get(sid)))
        common_count = len(common)
        accuracy_a = _ratio(correct_a_common, common_count)
        accuracy_b = _ratio(correct_b_common, common_count)
        delta_common = None if accuracy_a is None or accuracy_b is None else round(accuracy_a - accuracy_b, 4)

        correct_a = sum(1 for sid in answered_a if _is_correct(rows_a.get(sid)))
        correct_b = sum(1 for sid in answered_b if _is_correct(rows_b.get(sid)))
        share_a = _ratio(correct_a, total)
        share_b = _ratio(correct_b, total)
        delta_share = None if share_a is None or share_b is None else round(share_a - share_b, 4)

        primary = {
            "指标": PRIMARY_METRIC,
            "定义": PRIMARY_DEFINITION,
            "可比较": common_count > 0,
            "共同覆盖样本数": common_count,
            "共同覆盖样本": common,
            "正确数A": correct_a_common,
            "正确数B": correct_b_common,
            "准确率A": accuracy_a,
            "准确率B": accuracy_b,
            "差值": delta_common,
            "差值方向": "版本A - 版本B",
            "采用人群": "两个版本都给出预测的样本",
            "分母": f"共同覆盖样本数 {common_count}",
            "说明": (
                "两版本没有共同作答的样本，主比较不给出差值；"
                "请改用辅助比较查看各自实际正确答复了多少样本。"
                if common_count == 0
                else f"差值采用两版本共同作答的 {common_count} 个样本作分母，可直接比较。"
            ),
        }
        secondary = {
            "指标": SECONDARY_METRIC,
            "定义": SECONDARY_DEFINITION,
            "评估集样本总数": total,
            "正确数A": correct_a,
            "正确数B": correct_b,
            "占比A": share_a,
            "占比B": share_b,
            "差值": delta_share,
            "已作答A": len(answered_a),
            "已作答B": len(answered_b),
            "覆盖率A": _ratio(len(answered_a), total),
            "覆盖率B": _ratio(len(answered_b), total),
            "弃答A": total - len(answered_a),
            "弃答B": total - len(answered_b),
            "采用人群": "评估集全部样本",
            "分母": f"评估集样本总数 {total}",
            "说明": "弃答计入分母但不计为正确；两人分母一致，可直接比较实际正确答复量。",
        }

        groups = []
        for name in sorted(set(sample_group.values())):
            group_ids = {sid for sid, group in sample_group.items() if group == name}
            group_total = len(group_ids)
            group_common = [sid for sid in common if sid in group_ids]
            group_common_count = len(group_common)
            group_correct_a = sum(1 for sid in group_common if _is_correct(rows_a.get(sid)))
            group_correct_b = sum(1 for sid in group_common if _is_correct(rows_b.get(sid)))
            group_accuracy_a = _ratio(group_correct_a, group_common_count)
            group_accuracy_b = _ratio(group_correct_b, group_common_count)
            group_delta = (
                None if group_accuracy_a is None or group_accuracy_b is None
                else round(group_accuracy_a - group_accuracy_b, 4)
            )
            group_answered_a = answered_a & group_ids
            group_answered_b = answered_b & group_ids
            group_correct_all_a = sum(1 for sid in group_answered_a if _is_correct(rows_a.get(sid)))
            group_correct_all_b = sum(1 for sid in group_answered_b if _is_correct(rows_b.get(sid)))
            group_share_a = _ratio(group_correct_all_a, group_total)
            group_share_b = _ratio(group_correct_all_b, group_total)
            groups.append({
                "样本分组": name,
                "样本总数": group_total,
                "版本A": {
                    "已作答": len(group_answered_a),
                    "弃答": group_total - len(group_answered_a),
                    "正确": group_correct_all_a,
                    "命中率": _ratio(group_correct_all_a, len(group_answered_a)),
                    "覆盖率": _ratio(len(group_answered_a), group_total),
                    "正确响应占比": group_share_a,
                },
                "版本B": {
                    "已作答": len(group_answered_b),
                    "弃答": group_total - len(group_answered_b),
                    "正确": group_correct_all_b,
                    "命中率": _ratio(group_correct_all_b, len(group_answered_b)),
                    "覆盖率": _ratio(len(group_answered_b), group_total),
                    "正确响应占比": group_share_b,
                },
                "共同覆盖样本数": group_common_count,
                "共同覆盖样本": group_common,
                "共同覆盖准确率A": group_accuracy_a,
                "共同覆盖准确率B": group_accuracy_b,
                "主比较差值": group_delta,
                "可直接比较": group_common_count > 0,
                "不可比较原因": (
                    "" if group_common_count > 0
                    else "该分组两版本没有共同作答样本，主比较不给出差值"
                ),
                "主比较依据": f"采用该分组共同覆盖的 {group_common_count} 个样本作分母",
                "全组正确响应占比A": group_share_a,
                "全组正确响应占比B": group_share_b,
                "全组分母": group_total,
                "全组正确响应差值": (
                    None if group_share_a is None or group_share_b is None
                    else round(group_share_a - group_share_b, 4)
                ),
                "预测缺口": {
                    "仅A作答": sorted(group_answered_a - group_answered_b),
                    "仅B作答": sorted(group_answered_b - group_answered_a),
                    "两者弃答": sorted(group_ids - group_answered_a - group_answered_b),
                },
                "少数类别弃答A": [
                    sid for sid in sorted(group_ids - group_answered_a)
                    if str(sample_index[sid].get("真实分类")) in minority
                ],
                "少数类别弃答B": [
                    sid for sid in sorted(group_ids - group_answered_b)
                    if str(sample_index[sid].get("真实分类")) in minority
                ],
            })

        record = {
            "批次ID": batch_id,
            "评估批次": batch.get("批次编号"),
            "评估集编号": batch.get("评估集编号"),
            "评估集名称": batch.get("评估集名称"),
            "评估集样本总数": total,
            "模型A": model_a,
            "版本A": version_a,
            "模型B": model_b,
            "版本B": version_b,
            "比较口径": self.metric_definitions(),
            "主比较": primary,
            "辅助比较": secondary,
            "样本覆盖": {
                "共同覆盖": common,
                "仅A作答": only_a,
                "仅B作答": only_b,
                "两者弃答": both_abstained,
                "作答A": sorted(answered_a),
                "作答B": sorted(answered_b),
                "分母说明": {
                    "主比较": f"共同覆盖样本数 {common_count}",
                    "辅助比较": f"评估集样本总数 {total}",
                },
            },
            "分组": groups,
            "可直接比较分组": [group["样本分组"] for group in groups if group["可直接比较"]],
            "预测缺口分组": [group["样本分组"] for group in groups if not group["可直接比较"]],
            "少数类别": sorted(minority),
            "计算时间": _now(),
            "备注": str(note or ""),
        }

        if save:
            rows = store.rows(MODULE_COMPARISON)
            record["id"] = max((int(row.get("id", 0)) for row in rows), default=0) + 1
            record["比较编号"] = f"CMP-{record['id']:04d}"
            rows.append(record)
        else:
            record["id"] = None
            record["比较编号"] = None
        return record

    def list_comparisons(self, batch_id: int | None = None) -> list[dict[str, Any]]:
        rows = list(store.rows(MODULE_COMPARISON))
        if batch_id is not None:
            rows = [row for row in rows if int(row.get("批次ID", 0)) == batch_id]
        summaries = []
        for row in sorted(rows, key=lambda item: int(item.get("id", 0)), reverse=True):
            primary = row.get("主比较", {})
            secondary = row.get("辅助比较", {})
            summaries.append({
                "id": row.get("id"),
                "比较编号": row.get("比较编号"),
                "评估批次": row.get("评估批次"),
                "评估集编号": row.get("评估集编号"),
                "评估集样本总数": row.get("评估集样本总数"),
                "模型A": row.get("模型A"),
                "版本A": row.get("版本A"),
                "模型B": row.get("模型B"),
                "版本B": row.get("版本B"),
                "主比较指标": primary.get("指标"),
                "主比较差值": primary.get("差值"),
                "主比较可比较": primary.get("可比较"),
                "共同覆盖样本数": primary.get("共同覆盖样本数"),
                "正确响应占比A": secondary.get("占比A"),
                "正确响应占比B": secondary.get("占比B"),
                "已作答A": secondary.get("已作答A"),
                "已作答B": secondary.get("已作答B"),
                "计算时间": row.get("计算时间"),
                "备注": row.get("备注"),
            })
        return summaries

    def get_comparison(self, comparison_id: int) -> dict[str, Any]:
        row = store.find(MODULE_COMPARISON, comparison_id)
        if row is None:
            raise EvalError(f"比较结果 {comparison_id} 不存在")
        return row

    def group_view(
        self,
        batch_id: int,
        *,
        model_a: str,
        version_a: str,
        model_b: str,
        version_b: str,
    ) -> dict[str, Any]:
        """看板分组评估视图：每组的预测缺口与哪些组可直接比较。"""
        comparison = self.compare(
            batch_id=batch_id,
            model_a=model_a,
            version_a=version_a,
            model_b=model_b,
            version_b=version_b,
            save=False,
        )
        groups = comparison["分组"]
        return {
            "评估批次": comparison["评估批次"],
            "评估集编号": comparison["评估集编号"],
            "评估集样本总数": comparison["评估集样本总数"],
            "模型A": model_a,
            "版本A": version_a,
            "模型B": model_b,
            "版本B": version_b,
            "主比较指标": PRIMARY_METRIC,
            "主比较定义": PRIMARY_DEFINITION,
            "主比较": comparison["主比较"],
            "辅助比较指标": SECONDARY_METRIC,
            "辅助比较定义": SECONDARY_DEFINITION,
            "辅助比较": comparison["辅助比较"],
            "分组": groups,
            "可直接比较分组": comparison["可直接比较分组"],
            "预测缺口分组": comparison["预测缺口分组"],
            "分母说明": comparison["样本覆盖"]["分母说明"],
        }
