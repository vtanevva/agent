def build_classification_input(
    *,
    raw_message_text: str,
    client_name: str | None = None,
    project_name: str | None = None,
    project_context: dict | None = None,
) -> str:
    parts: list[str] = []

    if client_name:
        parts.append(f"Client: {client_name}")

    if project_name:
        parts.append(f"Project: {project_name}")

    if project_context:
        summary = project_context.get("summary")
        current_status = project_context.get("current_status")
        current_priorities = project_context.get("current_priorities")
        blockers = project_context.get("blockers")
        next_steps = project_context.get("next_steps")

        if summary:
            parts.append(f"Project Summary: {summary}")
        if current_status:
            parts.append(f"Current Status: {current_status}")
        if current_priorities:
            parts.append(f"Current Priorities: {current_priorities}")
        if blockers:
            parts.append(f"Blockers: {blockers}")
        if next_steps:
            parts.append(f"Next Steps: {next_steps}")

    parts.append(f"Incoming Message: {raw_message_text.strip()}")

    return "\n".join(parts).strip()