import json
from fastapi import FastAPI, Query
from app.database import init_db, connect
from app.hh_client import HHClient
from app.scoring import load_profile, score_vacancy
from app.settings import get_settings

app = FastAPI(title="Silvana Career Agent", version="0.1.0")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/vacancies/search")
async def search_vacancies(query: str = Query(..., min_length=2), area: int = 1, per_page: int = 20):
    result = await HHClient().search_vacancies(query, area=area, per_page=per_page)
    profile = load_profile()
    prepared = []
    with connect() as conn:
        for item in result.get("items", []):
            score = score_vacancy(item, profile)
            employer = (item.get("employer") or {}).get("name")
            salary = item.get("salary") or {}
            record = {
                "id": item["id"],
                "name": item.get("name"),
                "employer": employer,
                "salary": item.get("salary"),
                "area": (item.get("area") or {}).get("name"),
                "url": item.get("alternate_url"),
                "published_at": item.get("published_at"),
                "match_score": score,
            }
            prepared.append(record)
            conn.execute(
                "INSERT OR REPLACE INTO vacancies (id,name,employer,salary_from,salary_to,currency,area,url,published_at,match_score,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item["id"], item.get("name"), employer, salary.get("from"),
                    salary.get("to"), salary.get("currency"),
                    (item.get("area") or {}).get("name"), item.get("alternate_url"),
                    item.get("published_at"), score, json.dumps(item, ensure_ascii=False)
                ),
            )
        conn.commit()
    prepared.sort(key=lambda x: x["match_score"], reverse=True)
    return {"found": result.get("found", 0), "items": prepared}

if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("app.main:app", host=s.app_host, port=s.app_port)
