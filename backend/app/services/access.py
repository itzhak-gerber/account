"""What a business's subscription allows: modules, and whether it is read-only.

Pure values and errors (no database), so permission checks can use them anywhere.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.errors import Forbidden
from app.models import Module


class ReadOnly(Forbidden):
    """No current subscription: everything can be viewed and exported, nothing changed."""

    code = "subscription_expired"


class ModuleNotIncluded(Forbidden):
    code = "module_not_included"


class QuotaExceeded(Forbidden):
    code = "quota_exceeded"


@dataclass(frozen=True)
class Access:
    subscription_id: uuid.UUID | None
    modules: frozenset[str] = frozenset()
    ends_on: date | None = None
    terms: dict[str, Any] = field(default_factory=dict)

    @property
    def read_only(self) -> bool:
        return self.subscription_id is None

    def has(self, module: Module) -> bool:
        return not self.read_only and module.value in self.modules

    def require_writable(self) -> None:
        if self.read_only:
            raise ReadOnly("The business's plan has ended; it is read-only")

    def require(self, module: Module) -> None:
        self.require_writable()
        if module.value not in self.modules:
            raise ModuleNotIncluded(
                f"The '{module}' module is not part of this business's plan", module=module.value
            )


NO_ACCESS = Access(subscription_id=None)
