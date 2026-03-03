"""
Fast file discovery and text search across a project directory.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---- Default file extensions for each language ----
CPP_EXTENSIONS = {'.cpp', '.h', '.hpp', '.cc', '.cxx', '.hxx', '.c', '.hh', '.inl', '.ipp'}
PYTHON_EXTENSIONS = {'.py'}
TCL_EXTENSIONS = {'.tcl'}
ALL_EXTENSIONS = CPP_EXTENSIONS | PYTHON_EXTENSIONS | TCL_EXTENSIONS

# ---- Directories to skip ----
SKIP_DIRS = {
    '.git', '.svn', '.hg', '__pycache__', 'node_modules', '.vs', '.vscode',
    'build', 'Build', 'out', 'cmake-build-debug', 'cmake-build-release',
    'Debug', 'Release', 'x64', 'x86', '.idea', 'third_party', '3rdparty',
}


@dataclass
class FileMatch:
    """A text match within a file."""
    file_path: str
    line_number: int
    line_content: str
    column: int = 0
    context_before: list[str] = None
    context_after: list[str] = None

    def __post_init__(self):
        if self.context_before is None:
            self.context_before = []
        if self.context_after is None:
            self.context_after = []


def discover_files(
    project_path: str,
    extensions: Optional[set[str]] = None,
    skip_dirs: Optional[set[str]] = None,
    max_file_size_mb: float = 10.0,
) -> list[str]:
    """
    Recursively discover source files in the project directory.

    Args:
        project_path: Root directory to scan
        extensions: File extensions to include (default: all supported)
        skip_dirs: Directory names to skip (default: common build/VCS dirs)
        max_file_size_mb: Skip files larger than this (in MB)

    Returns:
        List of absolute file paths
    """
    if extensions is None:
        extensions = CPP_EXTENSIONS
    if skip_dirs is None:
        skip_dirs = SKIP_DIRS

    max_size = int(max_file_size_mb * 1024 * 1024)
    files = []

    project_path = os.path.abspath(project_path)
    for root, dirs, filenames in os.walk(project_path, topdown=True):
        # Filter out skip directories (modifying dirs in-place for os.walk)
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in extensions:
                continue

            filepath = os.path.join(root, filename)
            try:
                if os.path.getsize(filepath) <= max_size:
                    files.append(filepath)
            except OSError:
                continue

    return sorted(files)


def search_text(
    pattern: str,
    file_list: list[str],
    case_sensitive: bool = True,
    whole_word: bool = False,
    context_lines: int = 0,
    max_matches_per_file: int = 100,
) -> list[FileMatch]:
    """
    Search for a text pattern across multiple files.

    Args:
        pattern: Text pattern or regex to search for
        file_list: List of file paths to search
        case_sensitive: Whether the search is case-sensitive
        whole_word: Whether to match whole words only
        context_lines: Number of context lines before/after each match
        max_matches_per_file: Maximum matches per file (prevents explosion)

    Returns:
        List of FileMatch objects
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    if whole_word:
        regex = re.compile(rf'\b{re.escape(pattern)}\b', flags)
    else:
        regex = re.compile(re.escape(pattern), flags)

    results = []

    for filepath in file_list:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except (OSError, PermissionError):
            continue

        file_matches = 0
        for i, line in enumerate(lines):
            match = regex.search(line)
            if match:
                ctx_before = []
                ctx_after = []
                if context_lines > 0:
                    start = max(0, i - context_lines)
                    ctx_before = [l.rstrip('\n\r') for l in lines[start:i]]
                    end = min(len(lines), i + context_lines + 1)
                    ctx_after = [l.rstrip('\n\r') for l in lines[i + 1:end]]

                results.append(FileMatch(
                    file_path=filepath,
                    line_number=i + 1,
                    line_content=line.rstrip('\n\r'),
                    column=match.start(),
                    context_before=ctx_before,
                    context_after=ctx_after,
                ))
                file_matches += 1
                if file_matches >= max_matches_per_file:
                    break

    return results


def get_files_containing(
    project_path: str,
    pattern: str,
    extensions: Optional[set[str]] = None,
    case_sensitive: bool = True,
    whole_word: bool = True,
) -> list[str]:
    """
    Quick check: which files contain a given symbol name?
    Returns deduplicated list of file paths.
    """
    files = discover_files(project_path, extensions=extensions)
    matches = search_text(pattern, files, case_sensitive=case_sensitive,
                          whole_word=whole_word)
    return sorted(set(m.file_path for m in matches))


def read_file_content(file_path: str) -> Optional[str]:
    """Safely read a file's content."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except (OSError, PermissionError):
        return None
