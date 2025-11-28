"""
Stub tool registry for backward compatibility.

This exists only so existing tool files can import register/ToolSchema without errors.
The registration does nothing - agents now call tool functions directly.
"""

from typing import Dict, Callable, List
from pydantic import BaseModel


class ToolSchema(BaseModel):
    """Stub ToolSchema - does nothing"""
    name: str
    description: str
    parameters: dict


def register(func: Callable, schema: ToolSchema):
    """Stub register - does nothing, just returns the function"""
    return func


def all_openai_schemas() -> List[dict]:
    """Stub - returns empty list"""
    return []


def call(name: str, **kwargs):
    """Stub - should never be called"""
    raise NotImplementedError("agent_core has been replaced by domain agents")

