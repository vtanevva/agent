import os
import requests


def create_grafik_task(list_id: str, title: str, description: str) -> str:
    token = (os.getenv("GRAFIK_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Missing GRAFIK_TOKEN.")

    if not list_id:
        raise RuntimeError("Missing Grafik list id.")

    api_base_url = (os.getenv("GRAFIK_API_BASE_URL") or "").strip().rstrip("/")
    if not api_base_url:
        raise RuntimeError("Missing GRAFIK_API_BASE_URL.")

    url = f"{api_base_url}/api/v2/list/{list_id}/task"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {"name": title, "description": description}

    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code >= 400:
        raise RuntimeError(f"Grafik API error {response.status_code}: {response.text}")

    return response.json()["id"]
