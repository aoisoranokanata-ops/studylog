"""spec/examples/*.json を spec/schemas/*.schema.json で検証する。

母艦・子機の実装を待たずに、仕様書・スキーマ・サンプルの三者が矛盾していないことを確認するための道具。
    python spec/validate_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # Windows のコンソールでも日本語を読めるように
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("jsonschema が必要です:  pip install jsonschema")
    raise SystemExit(2)

SPEC_DIR = Path(__file__).resolve().parent
EXAMPLES = SPEC_DIR / "examples"
SCHEMAS = SPEC_DIR / "schemas"

# スキーマは通るが、アプリ側の検証（仕様書 付録B）で拒否すべきもの
APP_LEVEL_ONLY = {"invalid-up-03-app-level-checks.json"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    validators = {
        "down": Draft202012Validator(load(SCHEMAS / "down.schema.json")),
        "up": Draft202012Validator(load(SCHEMAS / "up.schema.json")),
    }

    failures: list[str] = []
    for path in sorted(EXAMPLES.glob("*.json")):
        data = load(path)
        kind = data.get("kind")
        if kind not in validators:
            failures.append(f"{path.name}: kind が不正 ({kind!r})")
            continue

        errors = sorted(validators[kind].iter_errors(data), key=lambda e: list(e.path))
        should_pass = path.name.endswith("-valid.json") or path.name in APP_LEVEL_ONLY

        if should_pass and errors:
            failures.append(f"{path.name}: 通るべきなのに {len(errors)} 件のエラー")
            for err in errors[:5]:
                loc = "/".join(str(p) for p in err.path) or "(root)"
                failures.append(f"    {loc}: {err.message}")
        elif not should_pass and not errors:
            failures.append(f"{path.name}: 拒否されるべきなのに通ってしまった")
        else:
            mark = "OK  " if should_pass else "拒否"
            detail = "" if should_pass else f"（{len(errors)}件）"
            print(f"{mark} {path.name}{detail}")
            if not should_pass:
                for err in errors[:3]:
                    loc = "/".join(str(p) for p in err.path) or "(root)"
                    print(f"       - {loc}: {err.message.splitlines()[0][:100]}")

    # 正常な上りサンプルは includedIds と records の id 集合が一致すること（付録B-2）
    for path in sorted(EXAMPLES.glob("up-*-valid.json")):
        data = load(path)
        ids = {
            r["id"]
            for arr in data["records"].values()
            for r in arr
        }
        included = set(data["includedIds"])
        if ids != included:
            failures.append(
                f"{path.name}: includedIds 不一致 "
                f"（records のみ: {sorted(ids - included)} / includedIds のみ: {sorted(included - ids)}）"
            )

    print()
    if failures:
        print("失敗:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("すべて期待どおり。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
