"""模型评估结果数据集的口径测试：可离线运行，不依赖 FastAPI。

运行：cd backend && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.model_eval import EvalError, ModelEvalService  # noqa: E402
from app.store import Store  # noqa: E402


class ModelEvalCase(unittest.TestCase):
    def setUp(self) -> None:
        # 每个用例一份干净仓库，避免汇入用例污染比较用例。
        import app.store as store_module

        self._original = store_module.store
        store_module.store = Store()
        self.service = ModelEvalService()

    def tearDown(self) -> None:
        import app.store as store_module

        store_module.store = self._original

    def test_no_common_coverage_gives_no_delta(self) -> None:
        comparison = self.service.compare(
            batch_id=1,
            model_a="MODE-0001",
            version_a="v1.2",
            model_b="MODE-0002",
            version_b="v0.9",
            save=False,
        )
        primary = comparison["主比较"]
        self.assertFalse(primary["可比较"])
        self.assertEqual(primary["共同覆盖样本数"], 0)
        self.assertIsNone(primary["差值"])
        self.assertEqual(comparison["可直接比较分组"], [])

    def test_full_set_correct_response_share_uses_five_as_denominator(self) -> None:
        comparison = self.service.compare(
            batch_id=1,
            model_a="MODE-0001",
            version_a="v1.2",
            model_b="MODE-0002",
            version_b="v0.9",
            save=False,
        )
        secondary = comparison["辅助比较"]
        self.assertEqual(secondary["评估集样本总数"], 5)
        self.assertEqual(secondary["正确数A"], 2)
        self.assertEqual(secondary["正确数B"], 1)
        self.assertEqual(secondary["占比A"], 0.4)
        self.assertEqual(secondary["占比B"], 0.2)
        self.assertEqual(secondary["覆盖率A"], 0.4)
        self.assertEqual(secondary["覆盖率B"], 0.6)

    def test_abstain_is_not_counted_as_correct(self) -> None:
        metrics = self.service.version_metrics(1, "MODE-0001", "v1.2")
        self.assertEqual(metrics["已作答"], 2)
        self.assertEqual(metrics["弃答"], 3)
        self.assertEqual(metrics["正确"], 2)
        self.assertEqual(metrics["正确响应占比"], 0.4)
        self.assertEqual(metrics["命中率"], 1.0)
        # 金标为「人工复核」的样本在评估集中占 1/5，属于少数类别。
        self.assertIn("S005", metrics["少数类别弃答"])

    def test_group_comparison_has_basis_and_gap(self) -> None:
        comparison = self.service.compare(
            batch_id=2,
            model_a="MODE-0001",
            version_a="v1.3",
            model_b="MODE-0003",
            version_b="v2.0",
            save=False,
        )
        primary = comparison["主比较"]
        self.assertTrue(primary["可比较"])
        self.assertEqual(primary["共同覆盖样本数"], 4)
        self.assertEqual(primary["差值"], -0.5)
        self.assertEqual(primary["分母"], "共同覆盖样本数 4")

        for group in comparison["分组"]:
            self.assertIn("样本总数", group)
            self.assertEqual(group["全组分母"], group["样本总数"])
            self.assertIn("共同覆盖", group["主比较依据"])
            self.assertEqual(group["可直接比较"], group["共同覆盖样本数"] > 0)
            if not group["可直接比较"]:
                self.assertIsNone(group["主比较差值"])
                self.assertTrue(group["不可比较原因"])

        personal = next(item for item in comparison["分组"] if item["样本分组"] == "个人")
        self.assertEqual(personal["共同覆盖样本数"], 3)
        self.assertIn("S106", personal["预测缺口"]["仅A作答"])

    def test_saved_comparison_keeps_batch_and_coverage_after_version_switch(self) -> None:
        record = self.service.compare(
            batch_id=2,
            model_a="MODE-0001",
            version_a="v1.3",
            model_b="MODE-0003",
            version_b="v2.0",
            save=True,
        )
        # 模拟评审在其它批次/版本间切换后再打开。
        self.service.version_metrics(2, "MODE-0001", "v1.3")
        reopened = self.service.get_comparison(record["id"])
        self.assertEqual(reopened["评估批次"], "EVAL-0002")
        self.assertEqual(reopened["评估集样本总数"], 9)
        self.assertEqual(reopened["样本覆盖"]["分母说明"]["主比较"], "共同覆盖样本数 4")
        self.assertEqual(reopened["样本覆盖"]["共同覆盖"], ["S101", "S102", "S105", "S108"])

    def test_import_rejects_missing_samples_and_wrong_truth(self) -> None:
        summary, message = self.service.import_results({
            "评估批次": "EVAL-0001",
            "模型编号": "MODE-0003",
            "模型版本": "v9",
            "results": [{"样本编号": "S001", "真实分类": "通过", "预测分类": "通过"}],
        })
        self.assertIsNone(summary)
        self.assertIn("未汇入", message)

        summary, message = self.service.import_results({
            "评估批次": "EVAL-0001",
            "模型编号": "MODE-0003",
            "模型版本": "v9",
            "results": [
                {"样本编号": sample["样本编号"], "真实分类": "拒绝", "预测分类": ""}
                for sample in self.service.list_samples(1)
            ],
        })
        self.assertIsNone(summary)
        self.assertIn("真实分类", message)

    def test_import_marks_abstain_for_review(self) -> None:
        samples = self.service.list_samples(1)
        predictions = {"S001": "通过", "S002": "通过", "S003": "", "S004": "", "S005": ""}
        summary, message = self.service.import_results({
            "评估批次": "EVAL-0001",
            "模型编号": "MODE-0003",
            "模型版本": "v9",
            "results": [
                {
                    "样本编号": sample["样本编号"],
                    "真实分类": sample["真实分类"],
                    "预测分类": predictions[sample["样本编号"]],
                }
                for sample in samples
            ],
        })
        self.assertIsNotNone(summary)
        self.assertEqual(summary["样本总数"], 5)
        self.assertEqual(summary["已作答"], 2)
        self.assertEqual(summary["弃答"], 3)
        self.assertEqual(summary["正确"], 2)
        self.assertEqual(summary["少数类别弃答"], 1)
        self.assertIn("待人工复核", message)

        queue = self.service.review_queue(1)
        imported = [row for row in queue["items"] if row["模型版本"] == "v9"]
        self.assertEqual(len(imported), 3)
        self.assertTrue(all(row["复核原因"] for row in imported))

    def test_review_requires_conclusion_and_leaves_queue(self) -> None:
        queue = self.service.review_queue(1)
        row = queue["items"][0]
        entry, message = self.service.mark_reviewed(row["id"], {})
        self.assertIsNone(entry)
        self.assertIn("复核结论", message)
        entry, message = self.service.mark_reviewed(row["id"], {"复核结论": "按弃答归档"})
        self.assertIsNotNone(entry)
        self.assertEqual(entry["复核结论"], "按弃答归档")
        remaining = self.service.review_queue(1)["items"]
        self.assertNotIn(row["id"], [item["id"] for item in remaining])

    def test_comparing_same_version_is_rejected(self) -> None:
        with self.assertRaises(EvalError):
            self.service.compare(
                batch_id=1,
                model_a="MODE-0001",
                version_a="v1.2",
                model_b="MODE-0001",
                version_b="v1.2",
                save=False,
            )


if __name__ == "__main__":
    unittest.main()
