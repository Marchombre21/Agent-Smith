import textwrap
from typing import Any
from mcp.types import Tool, ResourceTemplate, Resource
from src.models import SandboxConfig

FINAL_ANSWER = (
    "def final_answer(answer: Any) -> NoReturn:\n"
    '    """Ends the execution and hands value to the agent as the final'
    " answer.\n\n"
    "    Args:\n"
    "        answer: The final answer.\n"
    '    """\n\n'
)

READ_RESOURCES = (
    "def read_resource(uri: str) -> str:\n"
    '    """Read a resource exposed by the server. You must'
    " specify the URI that corresponds to the desired resource. The function"
    ' returns either text or "[binary content]: <type>" if the result is'
    " binary data. If the URI is invalid or unknown, it raises a"
    " ResourceError.\n\n"
    "    Args:\n"
    "        uri: The uri corresponding to the wanted resource.\n"
    '    """\n\n'
)

FIRST_INSTRUCTS = "The variables will be persistent between calls.\n\n"


class ManualMaker:

    def __init__(
        self,
        tools: list[Tool],
        config: SandboxConfig,
        resources: list[Resource],
        resources_temp: list[ResourceTemplate],
    ):
        self.tools = tools
        self.config = config
        self.resources = resources
        self.resources_temp = resources_temp
        self.converter: dict[str, str] = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "null": "None",
            "array": "list",
            "object": "dict",
        }

    @staticmethod
    def _mime_suffix(mime_type: str | None) -> str:
        if mime_type and not mime_type.startswith("text/"):
            return f" [{mime_type}]"
        return ""

    def _python_type(self, schema: dict[str, Any]) -> str:

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
                result.append(self._python_type({**schema, "type": elem}))
            return " | ".join(result)
        if kind == "array":
            if "items" in schema:
                item_type = self._python_type(schema["items"])
                return f"list[{item_type}]"
            return "list"
        if kind == "object":
            add_prop = schema.get("additionalProperties")
            if isinstance(add_prop, dict):
                return f"dict[str, {self._python_type(add_prop)}]"
            return "dict"
        if kind is not None:
            return self.converter.get(kind, "Any")
        return "Any"

    def _accept_null(self, schema: dict[str, Any]) -> bool:
        if "anyOf" in schema:
            for schem in schema["anyOf"]:
                if self._accept_null(schema=schem):
                    return True
            return False
        kind = schema.get("type")
        if isinstance(kind, list):
            if "null" in kind:
                return True
        return kind == "null"

    def _make_signature(self, tool: Tool) -> str:
        result: str = "def "
        result += tool.name + "("
        args = tool.input_schema["properties"]
        required_args = tool.input_schema.get("required", [])
        typed_args: list[str] = []
        for arg_name, arg_type in args.items():
            default_arg = ""
            arg_py_type = self._python_type(arg_type)
            if arg_name not in required_args:
                if "default" in arg_type:
                    default_arg = " = " + repr(arg_type["default"])
                else:
                    default_arg = " = None"
                    if not self._accept_null(arg_type):
                        arg_py_type += " | None"
            typed_args.append(f"{arg_name}: {arg_py_type}{default_arg}")

        result += ", ".join(typed_args) + ") -> "
        if tool.output_schema is not None:
            wrapped = tool.output_schema.get("x-fastmcp-wrap-result")
            if wrapped:
                args_out = tool.output_schema["properties"]["result"]
            else:
                args_out = tool.output_schema
            result += self._python_type(args_out)
        else:
            result += "Any"
        return result + ":"

    def construct(self) -> str:
        manual = FIRST_INSTRUCTS
        manual += (
            "Authorized imports:\n\n"
            f"{', '.join(self.config.authorized_imports)}\n\n"
        )
        manual += FINAL_ANSWER
        for tool in self.tools:
            manual += self._make_signature(tool) + '\n    """'
            if tool.description:
                manual += (
                    textwrap.indent(tool.description, "    ").lstrip() + "\n"
                )
            if tool.input_schema is not None:
                args = tool.input_schema.get("properties")
                if args:
                    manual += "\n    Args:\n"
                    for name, arg in args.items():
                        description: str = ""
                        if arg.get("description"):
                            description = f": {arg['description']}"
                        manual += f"        {name}{description}\n"
            manual += '    """\n\n'
        if len(self.resources) > 0 or len(self.resources_temp) > 0:
            manual += READ_RESOURCES
        if len(self.resources) > 0:
            manual += "Resources (read with read_resource(uri)):\n"
            for resource in self.resources:
                manual += (
                    f"- {resource.uri}"
                    f"    {resource.description}"
                    f"{self._mime_suffix(resource.mime_type)}\n"
                )
        if len(self.resources_temp) > 0:
            manual += (
                "Resource templates (read with read_resource(uri),"
                " replace {param} before reading):\n"
            )
            for resource_temp in self.resources_temp:
                manual += (
                    f"- {resource_temp.uri_template}"
                    f"    {resource_temp.description}"
                    f"{self._mime_suffix(resource_temp.mime_type)}\n"
                )

        return manual
