from abc import ABC, abstractmethod
from fnmatch import fnmatch
import json
from ntpath import isabs
import os
import sys
import re
import base64
import shutil
import tempfile
from typing import Any, Optional
import zipfile
import importlib
import importlib.util
import inspect
import glob
import mimetypes
import asyncio
import threading


# =============================================================================
# Content Cache - Loads content from FalkorDB for DB-first file reading
# =============================================================================

# Import embedded defaults for prompts
from python.helpers.embedded_defaults import get_prompt_defaults

_PROMPT_DEFAULTS = get_prompt_defaults()


class ContentCache:
    """
    Cache for file content loaded from FalkorDB.
    DB only - no filesystem fallback. FalkorDB required.
    Falls back to embedded defaults for prompts if not in DB.
    """

    _instance: Optional["ContentCache"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._loaded = False
        self._enabled = True  # Can disable DB lookup

    @classmethod
    def get_instance(cls) -> "ContentCache":
        """Get singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def enable(self, enabled: bool = True) -> None:
        """Enable or disable DB-first lookup."""
        self._enabled = enabled

    def is_loaded(self) -> bool:
        """Check if cache has been loaded from DB."""
        return self._loaded

    def load_from_dict(self, content_map: dict[str, str]) -> None:
        """Load content from a dictionary (path -> content)."""
        self._cache = content_map.copy()
        self._loaded = True

    async def load_from_db(self) -> int:
        """Load all content from FalkorDB."""
        try:
            from python.helpers.graph_store import get_graph_store
            store = await get_graph_store()

            # Ensure canvas prompts are stored
            try:
                from python.helpers.canvas_prompts import store_canvas_prompts
                await store_canvas_prompts()
            except Exception:
                pass  # Canvas prompts are optional

            content_map = await store.get_all_content()
            self._cache = content_map
            self._loaded = True
            return len(content_map)
        except Exception:
            # DB not available - this is an error in DB-only mode
            self._loaded = False
            return 0

    def load_from_db_sync(self) -> int:
        """Synchronous wrapper for load_from_db."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't use asyncio.run in running loop
                return 0
        except RuntimeError:
            pass

        try:
            return asyncio.run(self.load_from_db())
        except Exception:
            return 0

    def get(self, path: str) -> Optional[str]:
        """Get content by path. Lazy-loads from DB on first access."""
        if not self._enabled:
            return None

        # Lazy load from DB if not loaded yet
        if not self._loaded:
            self.load_from_db_sync()

        # Normalize path
        path = path.replace("\\", "/").lstrip("/")

        # Check cache
        if path in self._cache:
            return self._cache[path]

        # Try loading single item from DB if not in cache
        content = self._load_single_from_db(path)
        if content is not None:
            self._cache[path] = content
            return content

        # Fall back to embedded defaults for prompts
        content = self._get_from_defaults(path)
        if content is not None:
            self._cache[path] = content
            # Also seed to DB for persistence
            self._seed_to_db(path, content)
            return content

        return None

    def _load_single_from_db(self, path: str) -> Optional[str]:
        """Load a single content item from DB."""
        try:
            from python.helpers.graph_store import get_graph_store
            loop = asyncio.new_event_loop()
            store = loop.run_until_complete(get_graph_store())
            content = loop.run_until_complete(store.get_content(path))
            loop.close()
            return content
        except Exception:
            return None

    def _get_from_defaults(self, path: str) -> Optional[str]:
        """Get content from embedded defaults."""
        # Try exact path match for prompts
        if path in _PROMPT_DEFAULTS:
            return _PROMPT_DEFAULTS[path]

        # Try with prompts/ prefix removed
        if path.startswith("prompts/"):
            key = path[8:]  # Remove "prompts/" prefix
            if key in _PROMPT_DEFAULTS:
                return _PROMPT_DEFAULTS[key]

        # Try filename only (for backward compatibility)
        filename = os.path.basename(path)
        if filename in _PROMPT_DEFAULTS:
            return _PROMPT_DEFAULTS[filename]

        return None

    def _seed_to_db(self, path: str, content: str) -> None:
        """Seed content to DB for persistence (fire and forget)."""
        try:
            from python.helpers.graph_store import get_graph_store
            loop = asyncio.new_event_loop()
            store = loop.run_until_complete(get_graph_store())
            loop.run_until_complete(store.save_content(path, content, content_type="prompt"))
            loop.close()
        except Exception:
            pass  # Non-critical, content still available from defaults

    def set(self, path: str, content: str) -> None:
        """Set content in cache."""
        path = path.replace("\\", "/").lstrip("/")
        self._cache[path] = content

    def has(self, path: str) -> bool:
        """Check if path exists in cache or defaults."""
        if not self._enabled:
            return False
        path = path.replace("\\", "/").lstrip("/")
        if path in self._cache:
            return True
        # Check embedded defaults
        return self._get_from_defaults(path) is not None

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._loaded = False


def get_content_cache() -> ContentCache:
    """Get the content cache singleton."""
    return ContentCache.get_instance()


def init_content_cache() -> int:
    """Initialize content cache from FalkorDB. Returns number of items loaded."""
    cache = get_content_cache()
    return cache.load_from_db_sync()


class VariablesPlugin(ABC):
    @abstractmethod
    def get_variables(self, file: str, backup_dirs: list[str] | None = None, **kwargs) -> dict[str, Any]:  # type: ignore
        pass


def load_plugin_variables(
    file: str, backup_dirs: list[str] | None = None, **kwargs
) -> dict[str, Any]:
    if not file.endswith(".md"):
        return {}

    if backup_dirs is None:
        backup_dirs = []

    try:
        # Create filename and directories list
        plugin_filename = basename(file, ".md") + ".py"
        directories = [dirname(file)] + backup_dirs
        plugin_file = find_file_in_dirs(plugin_filename, directories)
    except FileNotFoundError:
        plugin_file = None

    if plugin_file and exists(plugin_file):

        from python.helpers import extract_tools

        classes = extract_tools.load_classes_from_file(
            plugin_file, VariablesPlugin, one_per_file=False
        )
        for cls in classes:
            return cls().get_variables(file, backup_dirs, **kwargs)  # type: ignore < abstract class here is ok, it is always a subclass

        # load python code and extract variables variables from it
        # module = None
        # module_name = dirname(plugin_file).replace("/", ".") + "." + basename(plugin_file, '.py')

        # try:
        #     spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        #     if not spec:
        #         return {}
        #     module = importlib.util.module_from_spec(spec)
        #     sys.modules[spec.name] = module
        #     spec.loader.exec_module(module)  # type: ignore
        # except ImportError:
        #     return {}

        # if module is None:
        #     return {}

        # # Get all classes in the module
        # class_list = inspect.getmembers(module, inspect.isclass)
        # # Filter for classes that are subclasses of VariablesPlugin
        # # iterate backwards to skip imported superclasses
        # for cls in reversed(class_list):
        #     if cls[1] is not VariablesPlugin and issubclass(cls[1], VariablesPlugin):
        #         return cls[1]().get_variables()  # type: ignore
    return {}


from python.helpers.strings import sanitize_string


def parse_file(
    _filename: str, _directories: list[str] | None = None, _encoding="utf-8", **kwargs
):
    if _directories is None:
        _directories = []

    # Find the file in the directories
    absolute_path = find_file_in_dirs(_filename, _directories)

    # Read the file content
    with open(absolute_path, "r", encoding=_encoding) as f:
        # content = remove_code_fences(f.read())
        content = f.read()

    is_json = is_full_json_template(content)
    content = remove_code_fences(content)
    variables = load_plugin_variables(absolute_path, _directories, **kwargs) or {}  # type: ignore
    variables.update(kwargs)
    if is_json:
        content = replace_placeholders_json(content, **variables)
        obj = json.loads(content)
        # obj = replace_placeholders_dict(obj, **variables)
        return obj
    else:
        content = replace_placeholders_text(content, **variables)
        # Process include statements
        content = process_includes(
            # here we use kwargs, the plugin variables are not inherited
            content,
            _directories,
            **kwargs,
        )
        return content


def read_prompt_file(
    _file: str, _directories: list[str] | None = None, _encoding="utf-8", **kwargs
):
    """Read prompt from DB. No filesystem fallback."""
    if _directories is None:
        _directories = []

    # If filename contains folder path, extract it and add to directories
    if os.path.dirname(_file):
        folder_path = os.path.dirname(_file)
        _file = os.path.basename(_file)
        _directories = [folder_path] + _directories

    content = None
    base_dir = get_base_dir()

    # Load from DB via content cache
    cache = get_content_cache()

    # Try each directory to find content
    for directory in _directories:
        rel_path = os.path.join(directory, _file).replace("\\", "/")
        # Convert absolute to relative if needed
        if rel_path.startswith(base_dir):
            rel_path = os.path.relpath(rel_path, base_dir).replace("\\", "/")
        elif rel_path.startswith("/"):
            rel_path = rel_path.lstrip("/")

        cached = cache.get(rel_path)
        if cached is not None:
            content = cached
            break

    if content is None:
        raise FileNotFoundError(f"Prompt not found in DB: {_file} (searched: {_directories})")

    variables = load_plugin_variables(_file, _directories, **kwargs) or {}
    variables.update(kwargs)

    content = replace_placeholders_text(content, **variables)
    content = process_includes(content, _directories, **kwargs)

    return content


def read_file(relative_path: str, encoding="utf-8"):
    """Read file from DB."""
    cache = get_content_cache()
    cached = cache.get(relative_path)
    if cached is not None:
        return cached
    raise FileNotFoundError(f"Not in DB: {relative_path}")


def read_file_bin(relative_path: str):
    """Read binary file from DB (stored as base64)."""
    cache = get_content_cache()
    cached = cache.get(relative_path)
    if cached is not None:
        # Binary content stored as base64 in DB
        if cached.startswith("base64:"):
            return base64.b64decode(cached[7:])
        return cached.encode()
    raise FileNotFoundError(f"Not in DB: {relative_path}")


def read_file_base64(relative_path):
    """Read file from DB as base64."""
    cache = get_content_cache()
    cached = cache.get(relative_path)
    if cached is not None:
        if cached.startswith("base64:"):
            return cached[7:]
        return base64.b64encode(cached.encode()).decode("utf-8")
    raise FileNotFoundError(f"Not in DB: {relative_path}")


# =============================================================================
# Template Security - Prevents prompt injection via template placeholders
# =============================================================================

class TrustedString(str):
    """
    Marker class for strings that are system-generated and trusted.
    These will NOT be escaped when used in template substitution.
    Use for internal system values only, never for user input.
    """
    pass


def trusted(value: str) -> TrustedString:
    """Mark a string as trusted (system-generated). Will not be escaped in templates."""
    return TrustedString(value)


def escape_template_delimiters(text: str) -> str:
    """
    Escape template delimiters in untrusted input to prevent prompt injection.
    Converts {{ to { { and }} to } } (with zero-width space).
    This neutralizes any injection attempts while preserving readability.
    """
    if not isinstance(text, str):
        return text
    # Use Unicode zero-width space (U+200B) to break delimiter sequences
    # This is invisible but prevents template evaluation
    return text.replace("{{", "{\u200b{").replace("}}", "}\u200b}")


def _prepare_template_value(value: Any, for_json: bool = False) -> str:
    """
    Prepare a value for template substitution.
    - TrustedString values are used as-is (system-generated)
    - All other values are escaped to prevent injection
    """
    if isinstance(value, TrustedString):
        # Trusted system value - no escaping
        return json.dumps(str(value)) if for_json else str(value)

    if for_json:
        # For JSON templates, escape the string value, then JSON encode
        if isinstance(value, str):
            escaped = escape_template_delimiters(value)
            return json.dumps(escaped)
        elif isinstance(value, (dict, list)):
            # Recursively escape strings in complex structures
            escaped = _escape_structure(value)
            return json.dumps(escaped)
        else:
            return json.dumps(value)
    else:
        # For text templates, escape and convert to string
        strval = str(value)
        return escape_template_delimiters(strval)


def _escape_structure(obj: Any) -> Any:
    """Recursively escape template delimiters in nested structures."""
    if isinstance(obj, TrustedString):
        return str(obj)
    elif isinstance(obj, str):
        return escape_template_delimiters(obj)
    elif isinstance(obj, dict):
        return {k: _escape_structure(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_escape_structure(item) for item in obj]
    else:
        return obj


def replace_placeholders_text(_content: str, **kwargs):
    """
    Replace placeholders with values from kwargs.
    All values are escaped unless marked as TrustedString.
    """
    for key, value in kwargs.items():
        placeholder = "{{" + key + "}}"
        strval = _prepare_template_value(value, for_json=False)
        _content = _content.replace(placeholder, strval)
    return _content


def replace_placeholders_json(_content: str, **kwargs):
    """
    Replace placeholders with JSON-encoded values from kwargs.
    All values are escaped unless marked as TrustedString.
    """
    for key, value in kwargs.items():
        placeholder = "{{" + key + "}}"
        strval = _prepare_template_value(value, for_json=True)
        _content = _content.replace(placeholder, strval)
    return _content


def replace_placeholders_dict(_content: dict, **kwargs):
    """Replace placeholders in dict structure. Values are escaped unless trusted."""
    def replace_value(value):
        if isinstance(value, str):
            placeholders = re.findall(r"{{(\w+)}}", value)
            if placeholders:
                for placeholder in placeholders:
                    if placeholder in kwargs:
                        replacement = kwargs[placeholder]
                        if value == f"{{{{{placeholder}}}}}":
                            # Full replacement - escape if needed
                            if isinstance(replacement, TrustedString):
                                return str(replacement)
                            return _escape_structure(replacement)
                        elif isinstance(replacement, (dict, list)):
                            escaped = _escape_structure(replacement)
                            value = value.replace(
                                f"{{{{{placeholder}}}}}", json.dumps(escaped)
                            )
                        else:
                            escaped = _prepare_template_value(replacement, for_json=False)
                            value = value.replace(
                                f"{{{{{placeholder}}}}}", escaped
                            )
            return value
        elif isinstance(value, dict):
            return {k: replace_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [replace_value(item) for item in value]
        else:
            return value

    return replace_value(_content)


def process_includes(_content: str, _directories: list[str], **kwargs):
    # Regex to find {{ include 'path' }} or {{include'path'}}
    include_pattern = re.compile(r"{{\s*include\s*['\"](.*?)['\"]\s*}}")

    def replace_include(match):
        include_path = match.group(1)
        # if the path is absolute, do not process it
        if os.path.isabs(include_path):
            return match.group(0)
        # Search for the include file in the directories
        try:
            included_content = read_prompt_file(include_path, _directories, **kwargs)
            return included_content
        except FileNotFoundError:
            return match.group(0)  # Return original if file not found

    # Replace all includes with the file content
    return re.sub(include_pattern, replace_include, _content)


def find_file_in_dirs(_filename: str, _directories: list[str]):
    """
    This function searches for a filename in a list of directories in order.
    Returns the absolute path of the first found file.
    """
    # Loop through the directories in order
    for directory in _directories:
        # Create full path
        full_path = get_abs_path(directory, _filename)
        if exists(full_path):
            return full_path

    # If the file is not found, raise FileNotFoundError
    raise FileNotFoundError(
        f"File '{_filename}' not found in any of the provided directories."
    )


def get_unique_filenames_in_dirs(dir_paths: list[str], pattern: str = "*"):
    # returns absolute paths for unique filenames, priority by order in dir_paths
    seen = set()
    result = []
    for dir_path in dir_paths:
        full_dir = get_abs_path(dir_path)
        for file_path in glob.glob(os.path.join(full_dir, pattern)):
            fname = os.path.basename(file_path)
            if fname not in seen and os.path.isfile(file_path):
                seen.add(fname)
                result.append(get_abs_path(file_path))
    # sort by filename (basename), not the full path
    result.sort(key=lambda path: os.path.basename(path))
    return result


def remove_code_fences(text):
    # Pattern to match code fences with optional language specifier
    pattern = r"(```|~~~)(.*?\n)(.*?)(\1)"

    # Function to replace the code fences
    def replacer(match):
        return match.group(3)  # Return the code without fences

    # Use re.DOTALL to make '.' match newlines
    result = re.sub(pattern, replacer, text, flags=re.DOTALL)

    return result


def is_full_json_template(text):
    # Pattern to match the entire text enclosed in ```json or ~~~json fences
    pattern = r"^\s*(```|~~~)\s*json\s*\n(.*?)\n\1\s*$"
    # Use re.DOTALL to make '.' match newlines
    match = re.fullmatch(pattern, text.strip(), flags=re.DOTALL)
    return bool(match)


def write_file(relative_path: str, content: str, encoding: str = "utf-8"):
    abs_path = get_abs_path(relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    content = sanitize_string(content, encoding)
    with open(abs_path, "w", encoding=encoding) as f:
        f.write(content)


def write_file_secure(relative_path: str, content: str, encoding: str = "utf-8"):
    """Write file with secure permissions (600) - owner read/write only.
    Use for sensitive files like settings and secrets fallbacks."""
    import stat

    abs_path = get_abs_path(relative_path)
    dir_path = os.path.dirname(abs_path)

    # Create directory with secure permissions (700)
    os.makedirs(dir_path, exist_ok=True)
    try:
        os.chmod(dir_path, stat.S_IRWXU)  # 700 - owner only
    except OSError:
        pass  # May fail on some filesystems

    content = sanitize_string(content, encoding)

    # Write file
    with open(abs_path, "w", encoding=encoding) as f:
        f.write(content)

    # Set secure permissions (600) - owner read/write only
    try:
        os.chmod(abs_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass  # May fail on some filesystems


def write_file_encrypted(relative_path: str, content: str, key: Optional[bytes] = None):
    """Write file with encryption. Falls back to secure write if encryption unavailable.
    Use for highly sensitive files."""
    import stat
    import hashlib

    abs_path = get_abs_path(relative_path)
    dir_path = os.path.dirname(abs_path)

    # Create directory with secure permissions
    os.makedirs(dir_path, exist_ok=True)
    try:
        os.chmod(dir_path, stat.S_IRWXU)  # 700
    except OSError:
        pass

    # Try to encrypt
    encrypted = False
    try:
        from cryptography.fernet import Fernet

        # Generate or use provided key
        if key is None:
            # Derive key from machine-specific data
            from python.helpers.runtime import get_persistent_id
            machine_id = get_persistent_id()
            key = base64.urlsafe_b64encode(hashlib.sha256(machine_id.encode()).digest())

        fernet = Fernet(key)
        encrypted_content = fernet.encrypt(content.encode('utf-8'))

        with open(abs_path, "wb") as f:
            f.write(b"ENCRYPTED:" + encrypted_content)
        encrypted = True
    except ImportError:
        pass  # cryptography not available
    except Exception:
        pass  # encryption failed

    if not encrypted:
        # Fallback to plain secure write
        content = sanitize_string(content, "utf-8")
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Set secure permissions
    try:
        os.chmod(abs_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass


def read_file_encrypted(relative_path: str, key: Optional[bytes] = None) -> Optional[str]:
    """Read encrypted file. Returns None if decryption fails."""
    import hashlib

    abs_path = get_abs_path(relative_path)

    if not os.path.exists(abs_path):
        return None

    with open(abs_path, "rb") as f:
        data = f.read()

    # Check if encrypted
    if data.startswith(b"ENCRYPTED:"):
        try:
            from cryptography.fernet import Fernet
            from python.helpers.runtime import get_persistent_id

            if key is None:
                machine_id = get_persistent_id()
                key = base64.urlsafe_b64encode(hashlib.sha256(machine_id.encode()).digest())

            fernet = Fernet(key)
            decrypted = fernet.decrypt(data[10:])  # Skip "ENCRYPTED:" prefix
            return decrypted.decode('utf-8')
        except Exception:
            return None  # Decryption failed
    else:
        # Plain text file
        return data.decode('utf-8')


def write_file_bin(relative_path: str, content: bytes):
    abs_path = get_abs_path(relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(content)


def write_file_base64(relative_path: str, content: str):
    # decode base64 string to bytes
    data = base64.b64decode(content)
    abs_path = get_abs_path(relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)


def delete_dir(relative_path: str):
    # ensure deletion of directory without propagating errors
    abs_path = get_abs_path(relative_path)
    if os.path.exists(abs_path):
        # first try with ignore_errors=True which is the safest option
        shutil.rmtree(abs_path, ignore_errors=True)

        # if directory still exists, try more aggressive methods
        if os.path.exists(abs_path):
            try:
                # try to change permissions and delete again
                for root, dirs, files in os.walk(abs_path, topdown=False):
                    for name in files:
                        file_path = os.path.join(root, name)
                        os.chmod(file_path, 0o777)
                    for name in dirs:
                        dir_path = os.path.join(root, name)
                        os.chmod(dir_path, 0o777)

                # try again after changing permissions
                shutil.rmtree(abs_path, ignore_errors=True)
            except:
                # suppress all errors - we're ensuring no errors propagate
                pass


def move_dir(old_path: str, new_path: str):
    # rename/move the directory from old_path to new_path (both relative)
    abs_old = get_abs_path(old_path)
    abs_new = get_abs_path(new_path)
    if not os.path.isdir(abs_old):
        return  # nothing to rename
    try:
        os.rename(abs_old, abs_new)
    except Exception:
        pass  # suppress all errors, keep behavior consistent


# move dir safely, remove with number if needed
def move_dir_safe(src, dst, rename_format="{name}_{number}"):
    base_dst = dst
    i = 2
    while exists(dst):
        dst = rename_format.format(name=base_dst, number=i)
        i += 1
    move_dir(src, dst)
    return dst


# create dir safely, add number if needed
def create_dir_safe(dst, rename_format="{name}_{number}"):
    base_dst = dst
    i = 2
    while exists(dst):
        dst = rename_format.format(name=base_dst, number=i)
        i += 1
    create_dir(dst)
    return dst


def create_dir(relative_path: str):
    abs_path = get_abs_path(relative_path)
    os.makedirs(abs_path, exist_ok=True)


def list_files(relative_path: str, filter: str = "*"):
    abs_path = get_abs_path(relative_path)
    if not os.path.exists(abs_path):
        return []
    return [file for file in os.listdir(abs_path) if fnmatch(file, filter)]


def make_dirs(relative_path: str):
    abs_path = get_abs_path(relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)


def get_abs_path(*relative_paths):
    "Convert relative paths to absolute paths based on the base directory."
    return os.path.join(get_base_dir(), *relative_paths)


def deabsolute_path(path: str):
    "Convert absolute paths to relative paths based on the base directory."
    return os.path.relpath(path, get_base_dir())


def fix_dev_path(path: str):
    "On dev environment, convert /a0/... paths to local absolute paths"
    from python.helpers.runtime import is_development

    if is_development():
        if path.startswith("/a0/"):
            path = path.replace("/a0/", "")
    return get_abs_path(path)


def normalize_a0_path(path: str):
    "Convert absolute paths into /a0/... paths"
    if is_in_base_dir(path):
        deabs = deabsolute_path(path)
        return "/a0/" + deabs
    return path


def exists(*relative_paths):
    path = get_abs_path(*relative_paths)
    return os.path.exists(path)


def get_base_dir():
    # Get the base directory from the current file path
    base_dir = os.path.dirname(os.path.abspath(os.path.join(__file__, "../../")))
    return base_dir


def basename(path: str, suffix: str | None = None):
    if suffix:
        return os.path.basename(path).removesuffix(suffix)
    return os.path.basename(path)


def dirname(path: str):
    return os.path.dirname(path)


def is_in_base_dir(path: str):
    # check if the given path is within the base directory
    base_dir = get_base_dir()
    # normalize paths to handle relative paths and symlinks
    abs_path = os.path.abspath(path)
    # check if the absolute path starts with the base directory
    return os.path.commonpath([abs_path, base_dir]) == base_dir


def get_subdirectories(
    relative_path: str,
    include: str | list[str] = "*",
    exclude: str | list[str] | None = None,
):
    abs_path = get_abs_path(relative_path)
    if not os.path.exists(abs_path):
        return []
    if isinstance(include, str):
        include = [include]
    if isinstance(exclude, str):
        exclude = [exclude]
    return [
        subdir
        for subdir in os.listdir(abs_path)
        if os.path.isdir(os.path.join(abs_path, subdir))
        and any(fnmatch(subdir, inc) for inc in include)
        and (exclude is None or not any(fnmatch(subdir, exc) for exc in exclude))
    ]


def zip_dir(dir_path: str):
    full_path = get_abs_path(dir_path)
    zip_file_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
    base_name = os.path.basename(full_path)
    with zipfile.ZipFile(zip_file_path, "w", compression=zipfile.ZIP_DEFLATED) as zip:
        for root, _, files in os.walk(full_path):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, full_path)
                zip.write(file_path, os.path.join(base_name, rel_path))
    return zip_file_path


def move_file(relative_path: str, new_path: str):
    abs_path = get_abs_path(relative_path)
    new_abs_path = get_abs_path(new_path)
    os.makedirs(os.path.dirname(new_abs_path), exist_ok=True)
    os.rename(abs_path, new_abs_path)


def safe_file_name(filename: str) -> str:
    # Replace any character that's not alphanumeric, dash, underscore, or dot with underscore
    return re.sub(r"[^a-zA-Z0-9-._]", "_", filename)


def read_text_files_in_dir(
    dir_path: str, max_size: int = 1024 * 1024
) -> dict[str, str]:

    abs_path = get_abs_path(dir_path)
    if not os.path.exists(abs_path):
        return {}
    result = {}
    for file_path in [os.path.join(abs_path, f) for f in os.listdir(abs_path)]:
        try:
            if not os.path.isfile(file_path):
                continue
            if os.path.getsize(file_path) > max_size:
                continue
            mime, _ = mimetypes.guess_type(file_path)
            if mime is not None and not mime.startswith("text"):
                continue
            # Check if file is binary by reading a small chunk
            content = read_file(file_path)
            result[os.path.basename(file_path)] = content
        except Exception:
            continue
    return result

def list_files_in_dir_recursively(relative_path: str) -> list[str]:
    abs_path = get_abs_path(relative_path)
    if not os.path.exists(abs_path):
        return []
    result = []
    for root, dirs, files in os.walk(abs_path):
        for file in files:
            file_path = os.path.join(root, file)
            # Return relative path from the base directory
            rel_path = os.path.relpath(file_path, abs_path)
            result.append(rel_path)
    return result
    