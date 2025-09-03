from typing import Dict, Callable, List
from pydantic import BaseModel

class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict

_registry: Dict[str, tuple[Callable, ToolSchema]] = {}

def register(func: Callable, schema: ToolSchema):
    """Register a tool callable + its OpenAI function schema."""
    _registry[schema.name] = (func, schema)

def all_openai_schemas() -> List[dict]:
    """Return list[dict] ready for OpenAI function‑calling."""
    wrapped = []
    for _, schema in _registry.values():
        try:
            schema_dict = schema.model_dump()
            wrapped.append({
                "type": "function",
                "function": schema_dict
            })
        except Exception as e:
            print(f"Error dumping schema for {schema.name}: {e}")
            # Fallback to dict conversion
            try:
                schema_dict = {
                    "name": schema.name,
                    "description": schema.description,
                    "parameters": schema.parameters
                }
                wrapped.append({
                    "type": "function",
                    "function": schema_dict
                })
            except Exception as e2:
                print(f"Fallback also failed for {schema.name}: {e2}")
    return wrapped

def call(name: str, **kwargs):
    """Execute a registered tool by name."""
    func, _ = _registry[name]
    return func(**kwargs)
