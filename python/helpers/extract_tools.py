"""
Extract Tools - DB-only code loading for Vessels.

The graph database IS the filesystem. No fallback.
FalkorDB required - Vessels won't run without it.
"""

import re
import inspect
import asyncio
from types import ModuleType
from typing import Any, Type, TypeVar
from .dirty_json import DirtyJson
import regex
from fnmatch import fnmatch

T = TypeVar('T')


# =============================================================================
# JSON Parsing
# =============================================================================

def json_parse_dirty(json: str) -> dict[str, Any] | None:
    if not json or not isinstance(json, str):
        return None
    ext_json = extract_json_object_string(json.strip())
    if ext_json:
        try:
            data = DirtyJson.parse_string(ext_json)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
    return None


def extract_json_object_string(content):
    start = content.find('{')
    if start == -1:
        return ""
    end = content.rfind('}')
    if end == -1:
        return content[start:]
    return content[start:end + 1]


def extract_json_string(content):
    pattern = r'\{(?:[^{}]|(?R))*\}|\[(?:[^\[\]]|(?R))*\]|"(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
    match = regex.search(pattern, content)
    return match.group(0) if match else ""


def fix_json_string(json_string):
    def replace_unescaped_newlines(match):
        return match.group(0).replace('\n', '\\n')
    return re.sub(r'(?<=: ")(.*?)(?=")', replace_unescaped_newlines, json_string, flags=re.DOTALL)


# =============================================================================
# DB-Only Code Loading
# =============================================================================

async def load_module_from_db(name: str) -> ModuleType | None:
    """Load a module from the graph database."""
    from .code_registry import get_registry
    registry = await get_registry()
    return await registry.load(name)


async def load_classes_from_db(
    code_type: str,
    base_class: Type[T],
    pattern: str = "*"
) -> list[Type[T]]:
    """Load classes from the graph database."""
    classes = []
    from .code_registry import get_registry
    registry = await get_registry()
    names = await registry.list_registered(code_type)

    for name in sorted(names):
        if pattern != "*" and not fnmatch(name, pattern):
            continue

        module = await registry.load(name)
        if module:
            class_list = inspect.getmembers(module, inspect.isclass)
            for cls in reversed(class_list):
                if cls[1] is not base_class and issubclass(cls[1], base_class):
                    classes.append(cls[1])
                    break
    return classes


def _run_async(coro):
    """Run async code, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


def load_classes_from_folder(
    folder: str,
    name_pattern: str,
    base_class: Type[T],
    one_per_file: bool = True
) -> list[Type[T]]:
    """Load classes from DB. Folder path maps to code_type."""
    code_type = _folder_to_code_type(folder)
    return _run_async(load_classes_from_db(code_type, base_class, name_pattern))


def load_classes_from_file(
    file: str,
    base_class: type[T],
    one_per_file: bool = True
) -> list[type[T]]:
    """Load classes from DB by name."""
    import os
    name = os.path.basename(file).replace('.py', '')

    async def _load():
        from .code_registry import get_registry
        registry = await get_registry()
        module = await registry.load(name)
        if not module:
            return []

        classes = []
        class_list = inspect.getmembers(module, inspect.isclass)
        for cls in reversed(class_list):
            if cls[1] is not base_class and issubclass(cls[1], base_class):
                classes.append(cls[1])
                if one_per_file:
                    break
        return classes

    return _run_async(_load())


def _folder_to_code_type(folder: str) -> str:
    """Map folder path to code type."""
    folder_lower = folder.lower()
    if "tool" in folder_lower:
        return "tool"
    elif "extension" in folder_lower:
        return "extension"
    return "module"
