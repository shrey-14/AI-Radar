"""
scrapers/benchmarks/open_llm.py — AI Radar
Source: Open LLM Leaderboard (HuggingFace Datasets API, paginated)
Auth:   None required
Benchmarks: IFEval, BBH, MATH Lvl5, GPQA, MUSR, MMLU-PRO
"""
import time
import requests

DATASET_URL = "https://datasets-server.huggingface.co/rows"
PAGE_SIZE   = 100


def _fetch_page(offset: int, max_retries: int = 3) -> dict | None:
    for attempt in range(max_retries):
        try:
            r = requests.get(
                DATASET_URL,
                params={
                    "dataset": "open-llm-leaderboard/contents",
                    "config":  "default",
                    "split":   "train",
                    "offset":  offset,
                    "limit":   PAGE_SIZE,
                },
                timeout=30,
            )
            if r.status_code in (502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(2 ** attempt)
    return None


def _extract(r: dict) -> dict:
    model_id = r.get("fullname") or ""
    return {
        "source":            "open_llm_leaderboard",
        "id":                f"open_llm_{model_id.replace('/', '_')}",
        "model_id":          model_id,
        "model_display_name": model_id.split("/")[-1] if "/" in model_id else model_id,
        "hf_url":            f"https://huggingface.co/{model_id}",
        "architecture":      r.get("Architecture"),
        "model_type":        r.get("Type"),
        "base_model":        r.get("Base Model"),
        "params_billions":   r.get("#Params (B)"),
        "average_score":     r.get("Average ⬆️"),
        "ifeval_score":      r.get("IFEval"),
        "bbh_score":         r.get("BBH"),
        "math_score":        r.get("MATH Lvl 5"),
        "gpqa_score":        r.get("GPQA"),
        "musr_score":        r.get("MUSR"),
        "mmlu_pro_score":    r.get("MMLU-PRO"),
        "precision":         r.get("Precision"),
        "license":           r.get("Hub License"),
        "hf_likes":          r.get("Hub ❤️"),
        "submission_date":   (r.get("Submission Date") or "")[:10] or None,
        "is_moe":            r.get("MoE", False),
        "flagged":           r.get("Flagged", False),
    }


def scrape(limit: int = 30, **kwargs) -> list[dict]:
    """
    Fetch top models from the Open LLM Leaderboard.
    Downloads all rows (paginated) then returns top N by average score.
    """
    all_rows = []
    offset   = 0
    total    = None

    while True:
        data = _fetch_page(offset)
        if data is None:
            offset += PAGE_SIZE
            if total and offset >= total:
                break
            continue

        if total is None:
            total = data.get("num_rows_total", 0)

        batch = data.get("rows", [])
        all_rows.extend(batch)

        if len(batch) < PAGE_SIZE or len(all_rows) >= total:
            break

        offset += PAGE_SIZE
        time.sleep(0.05)

    leaderboard = [_extract(row["row"]) for row in all_rows]

    top = sorted(
        [m for m in leaderboard if m["average_score"] and not m["flagged"]],
        key=lambda x: x["average_score"],
        reverse=True,
    )

    return top[:limit]
