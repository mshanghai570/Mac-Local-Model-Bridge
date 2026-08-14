"""
Deterministic, resource-aware model router for Local AI Gateway.
"""
from typing import Dict, List, Optional
from .config import config
from .models import ChatMessage

class ModelRouter:
    """
    Deterministic Model Router resolving aliases and tasks (fast, coding, reasoning, vision)
    with resource awareness and predictable fallbacks.
    """
    def __init__(self):
        self.aliases: Dict[str, str] = dict(config.model_aliases)

    def resolve_model(
        self,
        requested_model: Optional[str] = None,
        task: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        prompt: Optional[str] = None,
        has_images: bool = False
    ) -> str:
        """
        Resolves model name from explicit request, task, alias, or 'auto' logic.
        """
        # 1. Check explicit task routing first (e.g. task="coding")
        if task:
            task_clean = task.lower().strip()
            if task_clean in self.aliases:
                return self.aliases[task_clean]

        model_name = (requested_model or config.default_model).strip()

        # 2. Check if direct alias match
        if model_name.lower() in self.aliases:
            return self.aliases[model_name.lower()]

        # 3. Handle 'auto' routing
        if model_name.lower() in ("auto", "automatic", "default"):
            if not config.enable_auto_routing:
                return config.default_model
            return self._auto_select_model(messages, prompt, has_images)

        # 4. Resource check guard (prevent routing failure)
        return self._apply_resource_guard(model_name)

    def _auto_select_model(
        self,
        messages: Optional[List[ChatMessage]] = None,
        prompt: Optional[str] = None,
        has_images: bool = False
    ) -> str:
        # 1. Vision priority
        if has_images:
            return self.aliases.get("vision", "llava")
        if messages:
            for m in messages:
                if m.images and len(m.images) > 0:
                    return self.aliases.get("vision", "llava")

        # 2. Extract recent prompt text
        text_to_analyze = ""
        if prompt:
            text_to_analyze = prompt
        elif messages and len(messages) > 0:
            text_to_analyze = messages[-1].content or ""

        text_lower = text_to_analyze.lower()

        # 3. Coding heuristic
        code_indicators = [
            "```", "def ", "class ", "function", "import ", "const ", "let ", "var ",
            "return ", "fn ", "fn(", "int main", "public static", "syntax error",
            "regex", "sql", "query", "refactor", "bug", "traceback", "typescript",
            "python", "javascript", "swift", "rust", "dockerfile"
        ]
        if any(ind in text_lower for ind in code_indicators):
            return self.aliases.get("coding", "qwen2.5-coder")

        # 4. Reasoning / Math / Logic heuristic
        reasoning_indicators = [
            "step by step", "reasoning", "prove that", "derive", "calculate precisely",
            "logic puzzle", "riddle", "chain of thought", "theorem", "solve the equation",
            "analyze the argument", "philosophical"
        ]
        if any(ind in text_lower for ind in reasoning_indicators):
            return self.aliases.get("reasoning", "deepseek-r1:1.5b")

        # 5. Fast / Short prompt heuristic (<80 characters simple prompt)
        if len(text_to_analyze) < 80 and not any(k in text_lower for k in ["explain", "write a story", "detailed", "essay"]):
            return self.aliases.get("fast", config.default_model)

        # 6. General fallback
        return self.aliases.get("general", config.default_model)

    def _apply_resource_guard(self, model_name: str) -> str:
        """
        Guards against selecting oversized models if RAM is known to be insufficient.
        """
        try:
            import psutil
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            # If less than 6GB free, avoid 70b models that would freeze the Mac
            if "70b" in model_name.lower() and available_gb < 16.0:
                return self.aliases.get("general", config.default_model)
        except Exception:
            pass
        return model_name

    def get_aliases(self) -> Dict[str, str]:
        return dict(self.aliases)

    def set_alias(self, alias_name: str, target_model: str) -> None:
        self.aliases[alias_name.lower().strip()] = target_model.strip()

model_router = ModelRouter()
