from storage.sqlite_db import create_client, create_project, get_client_by_name, get_project_by_name


def ensure_client(client_name: str) -> int:
    client = get_client_by_name(client_name)
    return int(client["id"]) if client else create_client(client_name)


def ensure_client_project(client_name: str, project_name: str = "General") -> tuple[int, int]:
    client_id = ensure_client(client_name)

    project = get_project_by_name(client_id, project_name)
    project_id = int(project["id"]) if project else create_project(client_id, project_name)

    return client_id, project_id