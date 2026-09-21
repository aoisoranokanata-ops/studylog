"""UUID v4 の採番。"""

from __future__ import annotations

import uuid


def new_id() -> str:
    return str(uuid.uuid4())
