import os


def resolve_grafik_list_id_from_channel(channel: str) -> tuple[str | None, str | None, str | None]:
    entries: list[tuple[str, tuple[str, str, str]]] = [
        (
            os.getenv("SLACK_CHANNEL_MATT", ""),
            ("Matt", os.getenv("PROJECT_NAME_MATT", "General"), os.getenv("GRAFIK_LIST_ID", "")),
        ),
        (
            os.getenv("SLACK_CHANNEL_CLAUDELINE", ""),
            ("Claudeline", os.getenv("PROJECT_NAME_CLAUDELINE", "General"), os.getenv("GRAFIK_LIST2_ID", "")),
        ),
        (
            os.getenv("SLACK_CHANNEL_NICOLE", ""),
            ("Nicole", os.getenv("PROJECT_NAME_NICOLE", "General"), os.getenv("GRAFIK_LIST3_ID", "")),
        ),
    ]

    mapping: dict[str, tuple[str, str, str]] = {}
    for channel_id, value in entries:
        if channel_id:
            mapping[channel_id] = value

    if channel in mapping:
        client_name, project_name, list_id = mapping[channel]
        if list_id:
            return list_id, client_name, project_name
        return None, client_name, project_name

    default_list_id = os.getenv("GRAFIK_LIST_ID", "") or ""
    default_client = os.getenv("DEFAULT_CLIENT_NAME", "Matt")
    default_project = os.getenv("DEFAULT_PROJECT_NAME", "General")

    if default_list_id:
        return default_list_id, default_client, default_project

    return None, None, None

