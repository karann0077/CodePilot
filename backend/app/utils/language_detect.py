import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-cpp",
    ".scala": "scala",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".hs": "haskell",
    ".lhs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".jl": "julia",
    ".dart": "dart",
    ".groovy": "groovy",
    ".gvy": "groovy",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".xhtml": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".jsonc": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "conf",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "restructuredtext",
    ".tex": "latex",
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".hcl": "hcl",
    ".dockerfile": "dockerfile",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".vue": "vue",
    ".svelte": "svelte",
    ".elm": "elm",
    ".nim": "nim",
    ".zig": "zig",
    ".v": "v",
    ".d": "d",
    ".pas": "pascal",
    ".f90": "fortran",
    ".f95": "fortran",
    ".f03": "fortran",
    ".cmake": "cmake",
    ".make": "makefile",
    ".mk": "makefile",
    ".bat": "batch",
    ".cmd": "batch",
    ".asm": "assembly",
    ".s": "assembly",
    ".nix": "nix",
    ".pl": "perl",
    ".pm": "perl",
    ".tcl": "tcl",
    ".vb": "visualbasic",
    ".vba": "visualbasic",
    ".mat": "matlab",
    ".ipynb": "jupyter",
    ".sol": "solidity",
    ".wasm": "webassembly",
}

# Special filename -> language mappings (no extension)
FILENAME_MAP: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "podfile": "ruby",
    "fastfile": "ruby",
    "appfile": "ruby",
    "vagrantfile": "ruby",
    "brewfile": "ruby",
    "cmakelists.txt": "cmake",
    "requirements.txt": "text",
    "pipfile": "toml",
    ".gitignore": "gitignore",
    ".gitattributes": "gitattributes",
    ".env": "env",
    ".env.example": "env",
}


def detect_language(file_path: str) -> str:
    """Detect programming language from file path."""
    path = Path(file_path)
    filename_lower = path.name.lower()

    if filename_lower in FILENAME_MAP:
        return FILENAME_MAP[filename_lower]

    suffix = path.suffix.lower()
    return EXTENSION_MAP.get(suffix, "unknown")


def is_binary(file_path: str) -> bool:
    """Detect if a file is binary by reading first 8192 bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
        if b"\x00" in chunk:
            return True
        try:
            chunk.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True
    except (OSError, IOError) as exc:
        logger.warning("Could not read file %s for binary check: %s", file_path, exc)
        return True
