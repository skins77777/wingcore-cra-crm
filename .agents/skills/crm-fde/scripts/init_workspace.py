#!/usr/bin/env python3
"""Initialize a company's local CRM design records without overwriting files.

This tool does not connect to a CRM, execute workflows, or deploy anything.
Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


ASSETS = Path(__file__).resolve().parents[1] / "assets"
TEMPLATES = (
    "blueprint.md",
    "fields.md",
    "decisions.md",
    "implementation.md",
    "acceptance.md",
    "learning.md",
)


def initialize(project: Path, company_name: str, assets: Path = ASSETS) -> Path:
    """Create exactly one new record directory; existing state is never reused."""
    project = project.expanduser().resolve(strict=True)
    if not project.is_dir():
        raise ValueError("目标项目必须是已存在的目录。")
    company_name = company_name.strip()
    if not company_name or len(company_name) > 200:
        raise ValueError("公司名称需为 1–200 个字符。")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in company_name):
        raise ValueError("公司名称必须是单行文字，不含控制字符。")

    target = project / "crm-foundation"
    if target.exists() or target.is_symlink():
        raise FileExistsError("crm-foundation 已存在；请读取现有档案继续，不要重新初始化。")

    # Read every input before creating output, so missing templates leave no output.
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    contents = {}
    for name in TEMPLATES:
        source = assets / name
        if not source.is_file():
            raise FileNotFoundError(f"缺少模板：{name}")
        template = source.read_text(encoding="utf-8")
        contents[name] = template.replace("{{CREATED_AT}}", created_at).replace(
            "{{COMPANY_NAME}}", company_name
        )

    # mkdir is exclusive, including against a concurrent second invocation.
    target.mkdir(mode=0o700, exist_ok=False)
    for name, content in contents.items():
        with (target / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="已存在的客户项目目录")
    parser.add_argument("--company-name", required=True, help="用于本地档案标题的公司名称")
    args = parser.parse_args()
    try:
        target = initialize(args.project, args.company_name)
    except (OSError, ValueError) as exc:
        print(f"未完成初始化：{exc}", file=sys.stderr)
        print("没有覆盖或删除已有档案；若写入中途失败，请检查已生成内容。", file=sys.stderr)
        return 2
    print(f"已创建 {len(TEMPLATES)} 份本地工作文档：{target}")
    print("CRM 未连接、未配置、未部署；下一步读取 blueprint.md 开始教学与诊断。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
