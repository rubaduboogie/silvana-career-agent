from pathlib import Path
import yaml

PROFILE_PATH = Path("config/profile.yaml")

def load_profile():
    with PROFILE_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def score_vacancy(vacancy, profile):
    text = " ".join([
        vacancy.get("name") or "",
        vacancy.get("snippet", {}).get("requirement") or "",
        vacancy.get("snippet", {}).get("responsibility") or "",
    ]).lower()
    score = 0
    for keyword in profile.get("positive_keywords", []):
        if keyword.lower() in text:
            score += 8
    for keyword in profile.get("negative_keywords", []):
        if keyword.lower() in text:
            score -= 15
    salary = vacancy.get("salary") or {}
    salary_from = salary.get("from")
    minimum = profile.get("minimum_salary_rub", 0)
    if salary_from and salary.get("currency") == "RUR":
        score += 15 if salary_from >= minimum else -20
    return max(0, min(100, score))
