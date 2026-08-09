#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T1Mem / N1Mem-public 通用「根目录文档闸门」。
在 git commit 前检查：禁止在仓库根目录直接新增文档类文件
（*.html / *.md / *.pdf / *.pptx），必须归入子目录（如 docs/ 或各分类目录）。
白名单：仓库根允许的少量固定文件（README / LICENSE / claim_card / verify_public.py / start.html 等）。
退出码 0=放行，1=阻挡。
"""
import os
import subprocess
import sys

# 仓库根允许直接存在的文档/固定文件（白名单，大小写不敏感）
WHITELIST = {
    "readme.md", "readme.rst", "readme.txt",
    "license", "license.md", "license.txt",
    ".gitignore",
    "claim_card.html", "claim_card_en.html", "claim_card.json",
    "verify_public.py", "requirements.txt", "setup.py", "pyproject.toml",
    "start.html", "index.html",
}

DOC_EXTS = {".html", ".md", ".pdf", ".pptx"}


def main():
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL
        ).strip().decode("utf-8", "replace")
    except Exception:
        return 0  # 非仓库环境不阻挡

    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"], stderr=subprocess.DEVNULL
        ).decode("utf-8", "replace")
    except Exception:
        return 0

    bad = []
    for f in out.splitlines():
        f = f.strip()
        if not f or "/" in f:  # 子目录文件放行
            continue
        base = os.path.basename(f).lower()
        ext = os.path.splitext(base)[1]
        if ext in DOC_EXTS and base not in WHITELIST:
            bad.append(f)

    if bad:
        sys.stderr.write(
            "\n[doc-gate] \u2716 仓库根目录禁止散落文档，请归入子目录（如 docs/ 或对应分类）：\n"
        )
        for f in bad:
            sys.stderr.write("  - %s\n" % f)
        sys.stderr.write(
            "[doc-gate]   移入分类目录后再提交；紧急可用: git commit --no-verify\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
