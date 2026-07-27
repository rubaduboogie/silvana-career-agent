import httpx
from app.settings import get_settings

BASE_URL = "https://api.hh.ru"

class HHClient:
    def __init__(self):
        self.headers = {"User-Agent": get_settings().hh_user_agent}

    async def search_vacancies(self, text, area=1, per_page=20, page=0):
        params = {
            "text": text,
            "area": area,
            "per_page": min(per_page, 100),
            "page": page,
            "order_by": "publication_time",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{BASE_URL}/vacancies", params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()
