from mcp.types import Tool
from src.models import SandboxConfig


class ManualMaker():
    def __init__(self, tools: list[Tool], config: SandboxConfig):
        self.tools = tools
        self.config = config
        self.converter: dict[str, str] = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "null": "None",
            "array": "list",
            "object": "dict"
        }

    def _python_type(self, schema: dict) -> str:

        result: list[str] = []
        if "anyOf" in schema:
            for elem in schema["anyOf"]:
                result.append(self._python_type(elem))
            return " | ".join(result)
        if "enum" in schema:
            for elem in schema["enum"]:
                result.append(repr(elem))
            return f"Literal[{', '.join(result)}]"
        kind = schema.get("type")
        if isinstance(kind, list):
            for elem in kind:
                result.append(self.converter.get(elem, "Any"))
            return " | ".join(result)
        if kind == "array":
            if "items" in schema:
                item_type = self._python_type(schema["items"])
                return f"list[{item_type}]"
            return "list"
        if kind == "object":
            add_prop = schema.get("additionalProperties")
            if isinstance(add_prop, dict):
                return f'dict[str, {self._python_type(add_prop)}]'
            return "dict"
        if kind is not None:
            return self.converter.get(kind, "Any")
        return "Any"
