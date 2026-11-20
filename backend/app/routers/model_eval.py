"""模型评估结果数据集接口：批次、样本、结果汇入、人工复核、版本比较与分组视图。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.model_eval import EvalError, ModelEvalService

router = APIRouter(prefix="/api/model_eval", tags=["模型评估"])

service = ModelEvalService()


def _bad(error: EvalError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("/definitions")
def metric_definitions() -> dict[str, Any]:
    """比较口径：主比较、辅助比较、弃答与少数类别的处理方式。"""
    return service.metric_definitions()


@router.get("/batches")
def list_batches() -> dict[str, Any]:
    """评估批次清单：同一批次下的版本共享同一个评估集与同一份样本编号。"""
    items = service.list_batches()
    return {"items": items, "total": len(items)}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int) -> dict[str, Any]:
    """批次明细：评估集样本、真实分类分布与少数类别。"""
    try:
        return service.get_batch(batch_id)
    except EvalError as error:
        raise _bad(error) from error


@router.get("/batches/{batch_id}/samples")
def list_samples(batch_id: int) -> dict[str, Any]:
    """评估集样本清单：样本编号、真实分类、样本分组。"""
    try:
        items = service.list_samples(batch_id)
    except EvalError as error:
        raise _bad(error) from error
    return {"items": items, "total": len(items)}


@router.get("/batches/{batch_id}/versions")
def list_versions(batch_id: int) -> dict[str, Any]:
    """批次下已汇入的模型版本及各版本覆盖情况。"""
    try:
        items = service.list_versions(batch_id)
    except EvalError as error:
        raise _bad(error) from error
    return {"items": items, "total": len(items), "口径说明": service.metric_definitions()}


@router.get("/versions/detail")
def version_detail(
    batch_id: int = Query(description="评估批次 ID"),
    model: str = Query(description="模型编号"),
    version: str = Query(description="模型版本"),
) -> dict[str, Any]:
    """单版本明细：覆盖率、命中率、正确响应占比、混淆计数与分组命中率分母。"""
    try:
        return service.version_metrics(batch_id, model, version)
    except EvalError as error:
        raise _bad(error) from error


@router.get("/batches/{batch_id}/group-view")
def batch_group_view(
    batch_id: int,
    model_a: str = Query(description="版本 A 的模型编号"),
    version_a: str = Query(description="版本 A 的模型版本"),
    model_b: str = Query(description="版本 B 的模型编号"),
    version_b: str = Query(description="版本 B 的模型版本"),
) -> dict[str, Any]:
    """看板分组评估视图：一次性给出分组差值、可直接比较的类别与预测缺口。"""
    try:
        return service.group_view(
            batch_id,
            model_a=model_a,
            version_a=version_a,
            model_b=model_b,
            version_b=version_b,
        )
    except EvalError as error:
        raise _bad(error) from error


@router.post("/import", response_model=ActionResult)
def import_results(payload: EntryPayload) -> ActionResult:
    """从评估集汇入某个模型版本的逐样本结果；弃答要登记空预测，缺样本会被拦下。"""
    summary, message = service.import_results(payload.values)
    if summary is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=summary)


@router.get("/results", response_model=PageResult[dict])
def list_results(
    batch_id: int | None = Query(default=None, description="评估批次 ID"),
    model: str | None = Query(default=None, description="模型编号"),
    version: str | None = Query(default=None, description="模型版本"),
    prediction_status: str | None = Query(default=None, description="已作答 或 弃答"),
    group: str | None = Query(default=None, description="样本分组"),
    review_only: bool = Query(default=False, description="只看待人工复核的样本"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """逐样本结果：样本编号、真实分类、预测分类、复核原因；空预测即弃答。"""
    if size > 500:
        raise HTTPException(status_code=400, detail="每页最多 500 条，请缩小分页范围")
    items, total = service.list_results(
        batch_id=batch_id,
        model=model,
        version=version,
        prediction_status=prediction_status,
        group=group,
        review_only=review_only,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/review-queue")
def review_queue(batch_id: int | None = Query(default=None)) -> dict[str, Any]:
    """人工应复核清单：弃答、少数类别弃答与金标人工复核样本单列。"""
    return service.review_queue(batch_id)


@router.post("/results/{result_id}/review", response_model=ActionResult)
def mark_reviewed(result_id: int, payload: EntryPayload) -> ActionResult:
    """登记人工复核结论，结论回写到该样本结果行。"""
    entry, message = service.mark_reviewed(result_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/compare", response_model=ActionResult)
def create_comparison(payload: EntryPayload) -> ActionResult:
    """按共同覆盖准确率做版本比较，并把比较结果连同分母与样本覆盖一起留存。"""
    values = payload.values
    model_a = str(values.get("模型A") or values.get("model_a") or "").strip()
    version_a = str(values.get("版本A") or values.get("version_a") or "").strip()
    model_b = str(values.get("模型B") or values.get("model_b") or "").strip()
    version_b = str(values.get("版本B") or values.get("version_b") or "").strip()
    if not all([model_a, version_a, model_b, version_b]):
        return ActionResult(ok=False, message="请选择版本 A 与版本 B 的模型编号和模型版本")
    batch_id = values.get("批次ID") or values.get("batch_id")
    batch_code = values.get("评估批次") or values.get("batch_code")
    try:
        record = service.compare(
            batch_id=int(batch_id) if batch_id not in (None, "") else None,
            batch_code=str(batch_code) if batch_code else None,
            model_a=model_a,
            version_a=version_a,
            model_b=model_b,
            version_b=version_b,
            save=bool(values.get("留存", True)),
            note=str(values.get("备注") or ""),
        )
    except EvalError as error:
        return ActionResult(ok=False, message=str(error))
    primary = record["主比较"]
    if primary["可比较"]:
        message = (
            f"比较结果已留存：共同覆盖 {primary['共同覆盖样本数']} 个样本，"
            f"差值 {primary['差值']:+.2%}（版本A - 版本B）"
            if primary["差值"] is not None else "比较结果已留存"
        )
    else:
        message = "比较结果已留存：两版本没有共同覆盖样本，主比较不给出差值，请查看全评估集正确响应占比"
    return ActionResult(ok=True, message=message, entry=record)


@router.get("/comparisons")
def list_comparisons(batch_id: int | None = Query(default=None)) -> dict[str, Any]:
    """已留存的比较结果；切换版本后可在这里重新打开并核对评估批次与样本覆盖。"""
    items = service.list_comparisons(batch_id)
    return {"items": items, "total": len(items)}


@router.get("/comparisons/{comparison_id}")
def get_comparison(comparison_id: int) -> dict[str, Any]:
    """打开一条已留存的比较结果：含评估批次、样本覆盖、分母说明与分组明细。"""
    try:
        return service.get_comparison(comparison_id)
    except EvalError as error:
        raise _bad(error) from error


@router.get("/models/{model_code}/evaluations")
def model_evaluations(model_code: str) -> dict[str, Any]:
    """模型评估结果：该模型在各评估批次、各版本上的指标与分组明细。"""
    items = service.model_evaluations(model_code)
    return {"items": items, "total": len(items), "口径说明": service.metric_definitions()}
