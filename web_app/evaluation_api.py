"""因子评估 Web API

提供:
  GET  /api/evaluation/latest   — 最新因子评估结果
  GET  /api/evaluation/list     — 所有评估文件列表
"""

import json
import os
import logging
from pathlib import Path

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

eval_bp = Blueprint("evaluation", __name__, url_prefix="/api/evaluation")

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _find_latest_evaluation() -> Path | None:
    """找到 output 目录下最新的因子评估 JSON 文件"""
    if not OUTPUT_DIR.exists():
        return None

    files = sorted(OUTPUT_DIR.glob("factor_evaluation_*.json"), reverse=True)
    return files[0] if files else None


@eval_bp.route("/latest")
def latest_evaluation():
    """获取最新因子评估结果摘要"""
    filepath = _find_latest_evaluation()
    if filepath is None:
        return jsonify(
            {"success": False, "error": "未找到因子评估结果文件，请先运行因子评估"}
        )

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        ic_results = data.get("ic_results", {})

        # 构建 IC 汇总表
        ic_summary = []
        for factor_name, horizons in ic_results.items():
            for horizon_key, stats in horizons.items():
                ic_summary.append(
                    {
                        "factor": factor_name,
                        "horizon": horizon_key,
                        "ic_mean": round(stats.get("ic_mean", 0), 4),
                        "ic_std": round(stats.get("ic_std", 0), 4),
                        "ic_ir": round(stats.get("ic_ir", 0), 4),
                        "ic_positive_ratio": round(
                            stats.get("ic_positive_ratio", 0), 4
                        ),
                        "n_periods": stats.get("n_periods", 0),
                    }
                )

        # 因子综合评分
        scores = data.get("scores", [])

        # 因子相关性矩阵
        corr_matrix = data.get("correlation_matrix", [])
        factor_names = data.get("factor_names", [])

        return jsonify(
            {
                "success": True,
                "filename": filepath.name,
                "factor_names": factor_names,
                "horizons": data.get("horizons", []),
                "ic_summary": ic_summary,
                "scores": scores,
                "correlation_matrix": corr_matrix,
            }
        )

    except Exception as e:
        logger.error(f"读取因子评估文件失败: {e}")
        return jsonify({"success": False, "error": str(e)})


@eval_bp.route("/list")
def list_evaluations():
    """列出所有可用的评估文件"""
    if not OUTPUT_DIR.exists():
        return jsonify({"success": True, "files": []})

    files = sorted(OUTPUT_DIR.glob("factor_evaluation_*.json"), reverse=True)
    result = []
    for f in files:
        stat = f.stat()
        result.append(
            {
                "filename": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )

    return jsonify({"success": True, "files": result})
