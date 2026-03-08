from dataclasses import dataclass
from string import Template


@dataclass(frozen=True)
class PromptTemplate:
    system: str
    user: str


class PromptManager:
    """Central registry for prompt templates used across workflows."""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {
            "query": PromptTemplate(
                system=(
                    "You are CodePilot, an expert AI code assistant. "
                    "Answer accurately, concisely, and always cite evidence using file paths and line ranges."
                ),
                user=(
                    "Task: Answer the repository question using only the provided code context.\n\n"
                    "Context:\n$context\n\n"
                    "Question:\n$question\n\n"
                    "Output requirements:\n"
                    "- Provide direct answer first.\n"
                    "- Include evidence citations in [File: path Lx-y] format.\n"
                    "- Call out uncertainty explicitly if context is insufficient."
                ),
            ),
            "diagnose": PromptTemplate(
                system=(
                    "You are a debugging assistant. Analyze the error and code snippets. "
                    "Output each candidate in this exact format: "
                    "SUSPECT: <file_path>:<start_line>-<end_line> PROBABILITY:<0.0-1.0> REASON:<brief explanation>."
                ),
                user=(
                    "Task: Diagnose likely root-cause locations for the runtime issue.\n\n"
                    "Error input:\n$error_text\n\n"
                    "Context:\n$context\n\n"
                    "Return the most likely suspects first."
                ),
            ),
            "patch": PromptTemplate(
                system=(
                    "You are a code repair expert. Produce a minimal, correct unified diff. "
                    "Respect constraints and avoid unrelated edits."
                ),
                user=(
                    "Task: Generate a patch that fixes the issue.\n\n"
                    "Issue:\n$issue_description\n\n"
                    "Context:\n$context\n\n"
                    "Constraints:\n"
                    "- max_files_changed=2\n"
                    "- max_lines_changed=120\n"
                    "- Output unified diff with --- a/... +++ b/... and @@ hunks\n"
                    "- Then include a JSON object on a new line: "
                    '{"tests_to_run":["..."],"confidence_pct":75}\n'
                    "- Then include a Python unit test in a ```python``` block"
                ),
            ),
            "docs": PromptTemplate(
                system=(
                    "You are a documentation expert. Return concise, accurate docs. "
                    "Format response with sections: Docstring, Example, Complexity."
                ),
                user=(
                    "Generate documentation for this $language code:\n\n"
                    "$code\n\n"
                    "Return:\n"
                    "Docstring: <docstring>\n"
                    "Example:\n```python\n<usage example>\n```\n"
                    "Complexity: <complexity notes>"
                ),
            ),
        }

    def render(self, key: str, **values: str) -> tuple[str, str]:
        template = self._templates.get(key)
        if template is None:
            raise KeyError(f"Unknown prompt template: {key}")
        system = Template(template.system).safe_substitute(values)
        user = Template(template.user).safe_substitute(values)
        return system, user


_prompt_manager_instance: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    global _prompt_manager_instance
    if _prompt_manager_instance is None:
        _prompt_manager_instance = PromptManager()
    return _prompt_manager_instance
