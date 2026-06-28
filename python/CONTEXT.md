# Python Code Formatting Rules

Rules to apply when writing or reformatting any Python file.
Based on PEP 8, PEP 484 (type hints), and Google-style docstrings.

---

## 1. File Structure

Files must follow this top-to-bottom order:

1. Module docstring
2. Imports
3. Module-level logger
4. Constants
5. Dataclasses
6. Pure functions
7. Classes
8. Entry point (`main` + `if __name__ == "__main__"`)

---

## 2. Line Length

Maximum line length is **100 characters**.

---

## 3. Imports

- Use `from typing import List, Optional, Dict, ...` for type hints (do not use `from __future__ import annotations`).
- Group imports in this order, separated by a blank line:
 1. Standard library (`os`, `logging`, ...)
 2. Third-party packages
 3. Local modules

```python
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
```

---

## 4. Section Separators

Top-level separators span the full 100-character line width.
Sub-section separators (inside classes) use `# === Name ===` with 4-space indent.

### Top-level

```python
# ====================================================================================================
# Section Name
# ====================================================================================================
```

### Sub-section (inside class, 4-space indent)

```python
    # === Server ====================================================================================
```

Pad the right side with `=` to reach column 100.

---

## 5. Naming Conventions

| Element | Convention | Example |
|--------------------|------------------|--------------------------|
| Constants | `UPPER_SNAKE` | `MAX_RETRIES` |
| Functions | `snake_case` | `load_env` |
| Variables | `snake_case` | `sample_records` |
| Classes | `PascalCase` | `DataPipeline` |
| Private members | `_leading_under` | `self._config` |
| Type aliases | `PascalCase` | `RecordList` |

---

## 6. Type Hints

All functions, methods, and variables must have type hints.

```python
def load_env(key: str, default: Optional[str] = None) -> str:
 ...
```

Use `from typing import` for all generic types:
- `List[str]` not `list[str]`
- `Dict[str, str]` not `dict[str, str]`
- `Optional[str]` not `str | None`
- `Tuple[int, ...]` not `tuple[int, ...]`

---

## 7. Variable Alignment

When declaring a group of related variables, align the `:` and `=` operators so values line up vertically.

```python
MAX_RETRIES : int = 3
DEFAULT_TIMEOUT : float = 30.0
BASE_DIR : Path = Path(__file__).parent
```

Apply to:
- Module-level constants
- Dataclass fields
- `__init__` assignments (`self._x`)
- Any block of consecutive assignments

---

## 8. Keyword Argument Alignment

When calling a function with multiple keyword arguments on separate lines, align the `=` signs:

```python
config = Config(
 host = load_env("APP_HOST", "localhost"),
 port = int(load_env("APP_PORT", "8080")),
 tags = {"env": "production"},
)
```

---

## 9. Docstrings

### Single-line docstrings
Used only when the entire docstring fits on one line.

```python
def _save(self, record: dict) -> None:
 """Persist *record* to storage (stub for illustration)."""
```

### Multi-line docstrings
Opening `"""` on its own line, content follows, closing `"""` on its own line.

```python
def load_env(key: str, default: Optional[str] = None) -> str:
 """
 Read an environment variable, falling back to *default*.

 Args:
 key : Environment variable name.
 default : Value returned when the variable is absent.

 Returns:
 The variable's value, or *default* if unset.

 Raises:
 KeyError: If the variable is absent and no default is provided.
 """
```

### Docstring sections
Use Google style: `Args`, `Returns`, `Raises`, `Attributes`, `Example`.

Align `:` in `Args` and `Attributes` blocks so descriptions line up:

```python
Args:
 text : Raw input string.
 separator : Character used to replace spaces.
```

Include `Example` when the usage is non-obvious:

```python
Example:
 >>> slugify("Hello World")
 'hello-world'
```

---

## 10. Logging

Declare the logger at module level using `__name__`:

```python
logger = logging.getLogger(__name__)
```

Use `%`-style formatting in log calls (never f-strings):

```python
logger.warning("Skipping invalid record %r: %s", record, exc)
logger.info("Pipeline complete — %d/%d records processed.", len(results), len(records))
```

---

## 11. Error Handling

- Catch specific exceptions, never bare `except:`.
- Include descriptive messages with the offending value.

```python
raise ValueError(f"port must be 1–65535, got {self.port}")
raise KeyError(f"Required environment variable '{key}' is not set.")
```

- In loops, log and skip invalid items rather than aborting:

```python
except ValueError as exc:
 logger.warning("Skipping invalid record %r: %s", record, exc)
```

---

## 12. Dataclasses

- Use `@dataclass` for data-holding classes.
- Use `field(default_factory=...)` for mutable defaults.
- Validate in `__post_init__`.
- Align field type annotations and default values.

```python
@dataclass
class Config:
 host : str
 port : int = 8080
 retries : int = MAX_RETRIES
 tags : dict[str, str] = field(default_factory=dict)

 def __post_init__(self) -> None:
 if not (1 <= self.port <= 65_535):
 raise ValueError(f"port must be 1–65535, got {self.port}")
```

---

## 13. Classes

- Separate public and private sections with inner separators.
- Prefix private attributes and methods with `_`.
- Use keyword-only arguments (`*`) to prevent positional misuse:

```python
def __init__(self, config: Config, *, dry_run: bool = False) -> None:
```

---

## 14. Entry Point

Always guard execution with `if __name__ == "__main__"` and delegate logic to `main()`:

```python
def main() -> None:
 ...

if __name__ == "__main__":
 logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
 main()
```
