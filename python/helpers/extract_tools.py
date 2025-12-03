"""
Extract Tools - DB-first code loading for Vessels.

The graph database IS the filesystem. Code is loaded from DB first,
with filesystem as fallback for migration purposes.
"""

import re, os, importlib, importlib.util, inspect, asyncio
from types import ModuleType
from typing import Any, Type, TypeVar
from .dirty_json import DirtyJson
from .files import get_abs_path, deabsolute_path
import regex
from fnmatch import fnmatch

T = TypeVar('T')


# =============================================================================
# JSON Parsing (unchanged)
# =============================================================================

def json_parse_dirty(json:str) -> dict[str,Any] | None:
    if not json or not isinstance(json, str):
        return None
    ext_json = extract_json_object_string(json.strip())
    if ext_json:
        try:
            data = DirtyJson.parse_string(ext_json)
            if isinstance(data,dict): return data
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
    else:
        return content[start:end+1]

def extract_json_string(content):
    pattern = r'\{(?:[^{}]|(?R))*\}|\[(?:[^\[\]]|(?R))*\]|"(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
    match = regex.search(pattern, content)
    if match:
        return match.group(0)
    else:
        return ""

def fix_json_string(json_string):
    def replace_unescaped_newlines(match):
        return match.group(0).replace('\n', '\\n')
    fixed_string = re.sub(r'(?<=: ")(.*?)(?=")', replace_unescaped_newlines, json_string, flags=re.DOTALL)
    return fixed_string


# =============================================================================
# DB-First Code Loading
# =============================================================================

_db_module_cache: dict[str, ModuleType] = {}


async def load_module_from_db(name: str) -> ModuleType | None:
    """Load a module from the graph database."""
    if name in _db_module_cache:
        return _db_module_cache[name]

    try:
        from .code_registry import get_registry
        registry = await get_registry()
        module = await registry.load(name)
        if module:
            _db_module_cache[name] = module
            return module
    except Exception:
        pass
    return None


async def load_classes_from_db(
    code_type: str,
    base_class: Type[T],
    pattern: str = "*"
) -> list[Type[T]]:
    """
    Load classes from the graph database.

    Args:
        code_type: Type of code (tool, extension, module)
        base_class: Base class to filter for
        pattern: Name pattern to match

    Returns:
        List of classes that are subclasses of base_class
    """
    classes = []
    try:
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
                        break  # one per module
    except Exception:
        pass
    return classes


def load_classes_from_db_sync(
    code_type: str,
    base_class: Type[T],
    pattern: str = "*"
) -> list[Type[T]]:
    """Synchronous wrapper for load_classes_from_db."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't run async in running loop, fall back to filesystem
            return []
        return loop.run_until_complete(load_classes_from_db(code_type, base_class, pattern))
    except RuntimeError:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(load_classes_from_db(code_type, base_class, pattern))
        except Exception:
            return []


# =============================================================================
# Filesystem Loading (fallback / migration)
# =============================================================================

def import_module(file_path: str) -> ModuleType:
    """Import module from filesystem (fallback)."""
    abs_path = get_abs_path(file_path)
    module_name = os.path.basename(abs_path).replace('.py', '')

    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {abs_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_classes_from_folder(
    folder: str,
    name_pattern: str,
    base_class: Type[T],
    one_per_file: bool = True
) -> list[Type[T]]:
    """
    Load classes from folder. DB-first, filesystem fallback.

    Tries to load from DB first. If nothing found, falls back to filesystem
    and optionally migrates the code to DB.
    """
    # Try DB first
    code_type = _folder_to_code_type(folder)
    db_classes = load_classes_from_db_sync(code_type, base_class, name_pattern)
    if db_classes:
        return db_classes

    # Fallback to filesystem
    classes = []
    abs_folder = get_abs_path(folder)

    if not os.path.exists(abs_folder):
        return classes

    py_files = sorted(
        [f for f in os.listdir(abs_folder) if fnmatch(f, name_pattern) and f.endswith(".py")]
    )

    for file_name in py_files:
        file_path = os.path.join(abs_folder, file_name)
        try:
            module = import_module(file_path)
            class_list = inspect.getmembers(module, inspect.isclass)

            for cls in reversed(class_list):
                if cls[1] is not base_class and issubclass(cls[1], base_class):
                    classes.append(cls[1])
                    if one_per_file:
                        break
        except Exception:
            continue

    return classes


def load_classes_from_file(
    file: str,
    base_class: type[T],
    one_per_file: bool = True
) -> list[type[T]]:
    """Load classes from a single file. DB-first, filesystem fallback."""
    # Extract name from file path for DB lookup
    name = os.path.basename(file).replace('.py', '')

    # Try DB first
    try:
        from .code_registry import get_registry
        loop = asyncio.new_event_loop()
        registry = loop.run_until_complete(get_registry())
        module = loop.run_until_complete(registry.load(name))
        if module:
            class_list = inspect.getmembers(module, inspect.isclass)
            classes = []
            for cls in reversed(class_list):
                if cls[1] is not base_class and issubclass(cls[1], base_class):
                    classes.append(cls[1])
                    if one_per_file:
                        break
            if classes:
                return classes
    except Exception:
        pass

    # Fallback to filesystem
    classes = []
    module = import_module(file)
    class_list = inspect.getmembers(module, inspect.isclass)

    for cls in reversed(class_list):
        if cls[1] is not base_class and issubclass(cls[1], base_class):
            classes.append(cls[1])
            if one_per_file:
                break

    return classes


def _folder_to_code_type(folder: str) -> str:
    """Map folder path to code type."""
    folder_lower = folder.lower()
    if "tool" in folder_lower:
        return "tool"
    elif "extension" in folder_lower:
        return "extension"
    else:
        return "module"


# =============================================================================
# Migration Utilities
# =============================================================================

async def migrate_folder_to_db(folder: str, code_type: str = "module") -> int:
    """
    Migrate all Python files from a folder to the database.

    Returns number of files migrated.
    """
    from .code_registry import get_registry

    abs_folder = get_abs_path(folder)
    if not os.path.exists(abs_folder):
        return 0

    registry = await get_registry()
    migrated = 0

    py_files = [f for f in os.listdir(abs_folder) if f.endswith(".py")]

    for file_name in py_files:
        file_path = os.path.join(abs_folder, file_name)
        name = file_name.replace('.py', '')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            await registry.register(name, code, code_type)
            migrated += 1
        except Exception:
            continue

    return migrated


async def migrate_all_to_db() -> dict[str, int]:
    """Migrate all tools and extensions to DB."""
    results = {}

    # Migrate tools
    results["tools"] = await migrate_folder_to_db("python/tools", "tool")

    # Migrate extensions (each subfolder)
    extensions_base = get_abs_path("python/extensions")
    if os.path.exists(extensions_base):
        for ext_point in os.listdir(extensions_base):
            ext_folder = os.path.join(extensions_base, ext_point)
            if os.path.isdir(ext_folder):
                count = await migrate_folder_to_db(
                    f"python/extensions/{ext_point}",
                    "extension"
                )
                results[f"extension:{ext_point}"] = count

    return results
