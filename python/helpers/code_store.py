"""
A0 Framework - Code Store

Stores and indexes code files in FalkorDB for semantic search.
Enables A0 to be fully aware of its codebase - tools, instruments, helpers.

Usage:
    from python.helpers.code_store import CodeStore

    store = await CodeStore.get()
    await store.index_file("python/tools/my_tool.py")
    results = await store.search("tool that executes code")
"""

import ast
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
import json
import hashlib

from python.helpers.graph_store import GraphStore, get_graph_store
from python.helpers.print_style import PrintStyle
from python.helpers import files

if TYPE_CHECKING:
    from graphiti_core.nodes import EpisodeType


class CodeType(str, Enum):
    """Types of code artifacts."""
    TOOL = "tool"           # A0 tools
    EXTENSION = "extension" # A0 extensions
    HELPER = "helper"       # Helper modules
    API = "api"             # API endpoints
    INSTRUMENT = "instrument"  # Instrument scripts
    MODEL = "model"         # Data models
    CONFIG = "config"       # Configuration
    TEST = "test"           # Tests
    OTHER = "other"


@dataclass
class CodeEntity:
    """A code entity (class, function, etc.)."""
    name: str
    entity_type: str  # class, function, method, constant
    docstring: Optional[str] = None
    signature: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)  # For classes

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.entity_type,
            "docstring": self.docstring,
            "signature": self.signature,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "decorators": self.decorators,
            "bases": self.bases,
        }


@dataclass
class CodeFile:
    """Parsed code file with metadata."""
    path: str
    content: str
    code_type: CodeType
    language: str = "python"
    module_docstring: Optional[str] = None
    imports: list[str] = field(default_factory=list)
    entities: list[CodeEntity] = field(default_factory=list)
    hash: str = ""
    indexed_at: str = ""

    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        if not self.indexed_at:
            self.indexed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "code_type": self.code_type.value,
            "language": self.language,
            "module_docstring": self.module_docstring,
            "imports": self.imports,
            "entities": [e.to_dict() for e in self.entities],
            "hash": self.hash,
            "indexed_at": self.indexed_at,
        }

    def get_summary(self) -> str:
        """Generate a searchable summary of the code file."""
        parts = []

        # Add path and type
        parts.append(f"File: {self.path}")
        parts.append(f"Type: {self.code_type.value}")

        # Add module docstring
        if self.module_docstring:
            parts.append(f"Description: {self.module_docstring[:500]}")

        # Add classes
        classes = [e for e in self.entities if e.entity_type == "class"]
        if classes:
            class_names = ", ".join(c.name for c in classes)
            parts.append(f"Classes: {class_names}")
            for cls in classes:
                if cls.docstring:
                    parts.append(f"  {cls.name}: {cls.docstring[:200]}")
                if cls.bases:
                    parts.append(f"  {cls.name} inherits: {', '.join(cls.bases)}")

        # Add functions
        functions = [e for e in self.entities if e.entity_type == "function"]
        if functions:
            func_names = ", ".join(f.name for f in functions[:10])
            parts.append(f"Functions: {func_names}")
            for func in functions[:5]:
                if func.docstring:
                    parts.append(f"  {func.name}: {func.docstring[:150]}")

        # Add key imports
        if self.imports:
            key_imports = [i for i in self.imports if not i.startswith("_")][:10]
            parts.append(f"Imports: {', '.join(key_imports)}")

        return "\n".join(parts)


class PythonParser:
    """Parse Python files to extract metadata."""

    @staticmethod
    def parse(content: str, path: str) -> CodeFile:
        """Parse Python content and extract metadata."""
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            # Return basic info if parsing fails
            return CodeFile(
                path=path,
                content=content,
                code_type=PythonParser._infer_code_type(path),
                module_docstring=f"Parse error: {e}",
            )

        # Extract module docstring
        module_docstring = ast.get_docstring(tree)

        # Extract imports
        imports = PythonParser._extract_imports(tree)

        # Extract entities (classes, functions)
        entities = PythonParser._extract_entities(tree, content)

        # Infer code type from path and content
        code_type = PythonParser._infer_code_type(path, entities)

        return CodeFile(
            path=path,
            content=content,
            code_type=code_type,
            module_docstring=module_docstring,
            imports=imports,
            entities=entities,
        )

    @staticmethod
    def _extract_imports(tree: ast.AST) -> list[str]:
        """Extract import statements."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)
        return imports

    @staticmethod
    def _extract_entities(tree: ast.AST, content: str) -> list[CodeEntity]:
        """Extract classes and functions."""
        entities = []
        lines = content.split("\n")

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                entities.append(CodeEntity(
                    name=node.name,
                    entity_type="class",
                    docstring=ast.get_docstring(node),
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    decorators=[PythonParser._get_decorator_name(d) for d in node.decorator_list],
                    bases=[PythonParser._get_base_name(b) for b in node.bases],
                ))

                # Extract methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        entities.append(CodeEntity(
                            name=f"{node.name}.{item.name}",
                            entity_type="method",
                            docstring=ast.get_docstring(item),
                            signature=PythonParser._get_function_signature(item),
                            line_start=item.lineno,
                            line_end=item.end_lineno or item.lineno,
                            decorators=[PythonParser._get_decorator_name(d) for d in item.decorator_list],
                        ))

            elif isinstance(node, ast.FunctionDef):
                entities.append(CodeEntity(
                    name=node.name,
                    entity_type="function",
                    docstring=ast.get_docstring(node),
                    signature=PythonParser._get_function_signature(node),
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    decorators=[PythonParser._get_decorator_name(d) for d in node.decorator_list],
                ))

        return entities

    @staticmethod
    def _get_decorator_name(node: ast.expr) -> str:
        """Get decorator name as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{PythonParser._get_decorator_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return PythonParser._get_decorator_name(node.func)
        return "unknown"

    @staticmethod
    def _get_base_name(node: ast.expr) -> str:
        """Get base class name as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{PythonParser._get_base_name(node.value)}.{node.attr}"
        return "unknown"

    @staticmethod
    def _get_function_signature(node: ast.FunctionDef) -> str:
        """Get function signature."""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        return f"({', '.join(args)})"

    @staticmethod
    def _infer_code_type(path: str, entities: list[CodeEntity] = None) -> CodeType:
        """Infer code type from path and content."""
        path_lower = path.lower()

        if "/tools/" in path_lower:
            return CodeType.TOOL
        elif "/extensions/" in path_lower:
            return CodeType.EXTENSION
        elif "/helpers/" in path_lower:
            return CodeType.HELPER
        elif "/api/" in path_lower:
            return CodeType.API
        elif "/instruments/" in path_lower:
            return CodeType.INSTRUMENT
        elif "/models/" in path_lower or "models.py" in path_lower:
            return CodeType.MODEL
        elif "/test" in path_lower or "_test.py" in path_lower:
            return CodeType.TEST
        elif "config" in path_lower or "settings" in path_lower:
            return CodeType.CONFIG

        # Check entity bases for Tool, Extension, etc.
        if entities:
            for entity in entities:
                if entity.entity_type == "class":
                    if "Tool" in entity.bases:
                        return CodeType.TOOL
                    elif "Extension" in entity.bases:
                        return CodeType.EXTENSION
                    elif "ApiHandler" in entity.bases:
                        return CodeType.API

        return CodeType.OTHER


class CodeStore:
    """
    A0 Helper for storing and searching code in FalkorDB.

    Makes A0 aware of its entire codebase for self-modification,
    tool discovery, and code generation.
    """

    _instance: Optional["CodeStore"] = None

    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store

    @classmethod
    async def get(cls) -> "CodeStore":
        """Get or create CodeStore singleton."""
        if cls._instance is None:
            graph_store = await get_graph_store()
            cls._instance = cls(graph_store)
        return cls._instance

    async def index_file(self, path: str, base_dir: Optional[str] = None) -> Optional[CodeFile]:
        """
        Index a single code file.

        Args:
            path: Relative or absolute path to the file
            base_dir: Base directory for relative paths

        Returns:
            Parsed CodeFile or None if failed
        """
        if base_dir:
            abs_path = os.path.join(base_dir, path)
        else:
            abs_path = files.get_abs_path(path) if not os.path.isabs(path) else path

        if not os.path.exists(abs_path):
            PrintStyle.error(f"File not found: {abs_path}")
            return None

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            PrintStyle.error(f"Failed to read {abs_path}: {e}")
            return None

        # Normalize path to relative
        base = base_dir or files.get_abs_path("")
        rel_path = os.path.relpath(abs_path, base).replace("\\", "/")

        # Parse based on file extension
        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            code_file = PythonParser.parse(content, rel_path)
        else:
            # Basic indexing for non-Python files
            code_file = CodeFile(
                path=rel_path,
                content=content,
                code_type=CodeType.OTHER,
                language=ext.lstrip(".") or "text",
            )

        # Store in graph
        await self._store_code_file(code_file)

        return code_file

    async def _store_code_file(self, code_file: CodeFile) -> None:
        """Store a code file in the graph."""
        from graphiti_core.nodes import EpisodeType

        # Create searchable summary
        summary = code_file.get_summary()

        # Store full content
        content_data = json.dumps({
            "path": code_file.path,
            "content": code_file.content,
            "metadata": code_file.to_dict(),
        })

        # Delete existing if any
        await self._delete_code_file(code_file.path)

        # Store as episode for semantic search
        await self.graph_store.graphiti.add_episode(
            name=f"code:{code_file.path}",
            episode_body=f"{summary}\n\n---\n\n{code_file.content[:5000]}",  # Include some code for context
            source=EpisodeType.text,
            reference_time=datetime.now(timezone.utc),
            group_id=f"code:{code_file.code_type.value}",
        )

        # Also store full content for retrieval
        await self.graph_store.save_content(
            path=f"code/{code_file.path}",
            content=content_data,
            content_type="code",
        )

    async def _delete_code_file(self, path: str) -> None:
        """Delete a code file from the graph."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'code:{path}'
            DETACH DELETE n
            """
            await self.graph_store._driver.execute_query(query)
            await self.graph_store.delete_content(f"code/{path}")
        except Exception:
            pass

    async def search(
        self,
        query: str,
        code_type: Optional[CodeType] = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Search code by semantic query.

        Args:
            query: Natural language query (e.g., "tool that executes shell commands")
            code_type: Filter by code type
            limit: Maximum results

        Returns:
            List of matching code files with metadata
        """
        group_id = f"code:{code_type.value}" if code_type else None

        results = await self.graph_store.graphiti.search(
            query=query,
            num_results=limit,
            group_ids=[group_id] if group_id else None,
        )

        code_results = []
        for result in results:
            # Extract path from the result
            name = getattr(result, 'name', '') or ''
            if name.startswith("code:"):
                path = name[5:]
            else:
                # Try to extract from content
                content = getattr(result, 'fact', '') or str(result)
                path_match = re.search(r'File: ([^\n]+)', content)
                path = path_match.group(1) if path_match else "unknown"

            code_results.append({
                "path": path,
                "score": getattr(result, 'score', 1.0),
                "summary": getattr(result, 'fact', str(result))[:500],
            })

        return code_results

    async def get_code(self, path: str) -> Optional[dict]:
        """
        Get full code file content and metadata.

        Args:
            path: Relative path to the code file

        Returns:
            Dict with content and metadata, or None if not found
        """
        content = await self.graph_store.get_content(f"code/{path}")
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"path": path, "content": content, "metadata": {}}
        return None

    async def list_code(self, code_type: Optional[CodeType] = None) -> list[str]:
        """List all indexed code file paths."""
        all_paths = await self.graph_store.list_content("code")

        paths = []
        for p in all_paths:
            if p.startswith("code/"):
                rel_path = p[5:]  # Remove 'code/' prefix
                paths.append(rel_path)

        # Filter by type if specified
        if code_type:
            filtered = []
            for path in paths:
                data = await self.get_code(path)
                if data and data.get("metadata", {}).get("code_type") == code_type.value:
                    filtered.append(path)
            return filtered

        return paths

    async def index_directory(
        self,
        directory: str,
        patterns: list[str] = None,
        exclude: list[str] = None,
    ) -> int:
        """
        Index all code files in a directory.

        Args:
            directory: Directory to index
            patterns: File patterns to include (default: ["*.py"])
            exclude: Patterns to exclude

        Returns:
            Number of files indexed
        """
        import glob as glob_module

        if patterns is None:
            patterns = ["**/*.py"]

        if exclude is None:
            exclude = ["__pycache__", ".git", "node_modules", "venv", ".venv", "tmp"]

        base_dir = files.get_abs_path(directory) if not os.path.isabs(directory) else directory
        indexed = 0

        for pattern in patterns:
            full_pattern = os.path.join(base_dir, pattern)
            for file_path in glob_module.glob(full_pattern, recursive=True):
                # Check exclusions
                skip = False
                for exc in exclude:
                    if exc in file_path:
                        skip = True
                        break

                if skip:
                    continue

                rel_path = os.path.relpath(file_path, files.get_abs_path(""))
                result = await self.index_file(rel_path)
                if result:
                    indexed += 1
                    PrintStyle.standard(f"Indexed: {rel_path}")

        return indexed

    async def index_codebase(self) -> int:
        """
        Index the entire A0/Vessels codebase.

        Returns:
            Number of files indexed
        """
        directories = [
            "python/tools",
            "python/helpers",
            "python/extensions",
            "python/api",
            "instruments",
        ]

        total = 0
        for directory in directories:
            dir_path = files.get_abs_path(directory)
            if os.path.exists(dir_path):
                count = await self.index_directory(directory)
                total += count
                PrintStyle.standard(f"Indexed {count} files from {directory}")

        # Also index root Python files
        root_files = ["agent.py", "models.py", "initialize.py", "run_ui.py"]
        for file in root_files:
            file_path = files.get_abs_path(file)
            if os.path.exists(file_path):
                result = await self.index_file(file)
                if result:
                    total += 1

        PrintStyle.standard(f"Total indexed: {total} files")
        return total

    async def find_tool(self, description: str) -> Optional[dict]:
        """
        Find a tool by description.

        Convenience method for finding tools.
        """
        results = await self.search(description, code_type=CodeType.TOOL, limit=1)
        if results:
            return await self.get_code(results[0]["path"])
        return None

    async def find_extension(self, description: str) -> Optional[dict]:
        """Find an extension by description."""
        results = await self.search(description, code_type=CodeType.EXTENSION, limit=1)
        if results:
            return await self.get_code(results[0]["path"])
        return None

    async def find_helper(self, description: str) -> Optional[dict]:
        """Find a helper by description."""
        results = await self.search(description, code_type=CodeType.HELPER, limit=1)
        if results:
            return await self.get_code(results[0]["path"])
        return None
