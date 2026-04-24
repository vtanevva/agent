from storage.sqlite_db import (
    create_project,
    get_project_by_name,
    list_projects_for_client,
)


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _canonicalize_project_name(value: str) -> str:
    """
    Normalize a project name for consistent on-disk storage.

    Rules:
      - Collapse whitespace.
      - Apply Title Case, so "perry project" and "PERRY PROJECT" and
        "Perry project" all store as "Perry Project".
      - Preserve digit-prefixed tokens (``q4`` -> ``Q4``) via the
        standard library's ``str.title`` behavior.

    The SQLite lookup in ``get_project_by_name`` is case-insensitive, so
    hints that arrive with any casing will still reuse an existing row
    instead of creating a duplicate.
    """
    cleaned = " ".join((value or "").strip().split())
    if not cleaned:
        return ""
    return cleaned.title()


def _confidence_for_reason(reason: str) -> float:
    mapping = {
        "explicit_project_name": 1.0,
        "matched_project_name_in_text": 0.8,
        "single_known_project": 0.7,
        "fallback_existing_general": 0.3,
        "fallback_created_general": 0.3,
        "ambiguous_multiple_projects_needs_review": 0.2,
    }
    return mapping.get(reason, 0.5)


def _needs_review_for_reason(reason: str) -> bool:
    return reason == "ambiguous_multiple_projects_needs_review"


def resolve_project_for_client(
    *,
    client_id: int,
    text: str,
    explicit_project_name: str | None = None,
    fallback_project_name: str = "General",
) -> tuple[int, str, str, float, bool]:
    """
    Returns:
      (project_id, project_name, resolution_reason, project_confidence, needs_project_review)

    resolution_reason examples:
      - explicit_project_name
      - single_known_project
      - matched_project_name_in_text
      - fallback_existing_general
      - fallback_created_general
      - ambiguous_multiple_projects_needs_review
    """
    clean_text = _normalize(text)
    projects = list_projects_for_client(client_id)

    canonical_fallback = _canonicalize_project_name(fallback_project_name) or "General"

    # 1) Explicit project name from payload/manual input wins
    if explicit_project_name and explicit_project_name.strip():
        project_name = _canonicalize_project_name(explicit_project_name)
        existing = get_project_by_name(client_id, project_name)
        reason = "explicit_project_name"
        confidence = _confidence_for_reason(reason)
        needs_review = _needs_review_for_reason(reason)

        if existing:
            return int(existing["id"]), existing["name"], reason, confidence, needs_review

        project_id = create_project(client_id, project_name)
        return project_id, project_name, reason, confidence, needs_review

    # 2) If client has exactly one project, use it
    if len(projects) == 1:
        only_project = projects[0]
        reason = "single_known_project"
        confidence = _confidence_for_reason(reason)
        needs_review = _needs_review_for_reason(reason)
        return int(only_project["id"]), only_project["name"], reason, confidence, needs_review

    # 3) Try simple name matching against known project names
    sortable_projects = sorted(
        projects,
        key=lambda p: len((p.get("name") or "").strip()),
        reverse=True,
    )

    for project in sortable_projects:
        project_name = (project.get("name") or "").strip()
        if not project_name:
            continue

        normalized_project_name = _normalize(project_name)
        if normalized_project_name and normalized_project_name in clean_text:
            reason = "matched_project_name_in_text"
            confidence = _confidence_for_reason(reason)
            needs_review = _needs_review_for_reason(reason)
            return int(project["id"]), project_name, reason, confidence, needs_review

    # 4) If multiple projects exist and none matched, flag for review
    if len(projects) > 1:
        existing_fallback = get_project_by_name(client_id, canonical_fallback)
        reason = "ambiguous_multiple_projects_needs_review"
        confidence = _confidence_for_reason(reason)
        needs_review = _needs_review_for_reason(reason)

        if existing_fallback:
            return int(existing_fallback["id"]), existing_fallback["name"], reason, confidence, needs_review

        project_id = create_project(client_id, canonical_fallback)
        return project_id, canonical_fallback, reason, confidence, needs_review

    # 5) Reuse existing fallback project if present
    existing_fallback = get_project_by_name(client_id, canonical_fallback)
    if existing_fallback:
        reason = "fallback_existing_general"
        confidence = _confidence_for_reason(reason)
        needs_review = _needs_review_for_reason(reason)
        return int(existing_fallback["id"]), existing_fallback["name"], reason, confidence, needs_review

    # 6) Create fallback project
    project_id = create_project(client_id, canonical_fallback)
    reason = "fallback_created_general"
    confidence = _confidence_for_reason(reason)
    needs_review = _needs_review_for_reason(reason)
    return project_id, canonical_fallback, reason, confidence, needs_review