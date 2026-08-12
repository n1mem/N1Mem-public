#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T1Mem / N1Mem-public 通用「文档闸门」。
在 git commit 前检查两类违规：

① 根目录散落文档（对所有仓库）
   禁止在仓库根目录直接新增文档类文件（*.html / *.md / *.pdf / *.pptx），
   必须归入子目录（如 docs/ 或各分类目录）。
   白名单：README / LICENSE / claim_card / verify_public.py / start.html 等。

② 公开仓内部文档（仅 N1Mem-public 生效）
   公开仓只放对外可验证产物（claim_card* / README* / verify_public.py /
   repro_byok/* / .github/*）。禁止提交内部文档——文件名/路径含
   「复盘 / 补齐 / 对照 / 战略 / 投资人 / 口径卡 / 进度追踪 / PRD / 架构 / 内部」
   字样，或位于 docs/_archive/ 下任何文件。
   （2026-08-12 因 docs/_archive/架构全面复盘报告_v5.html 误公开而补此规则）

退出码 0=放行，1=阻挡。
"""
import os
import subprocess
import sys

# 仓库根允许直接存在的文档/固定文件（白名单，大小写不敏感）
WHITELIST = {
    "readme.md", "readme.rst", "readme.txt",
    "readme.zh.md", "readme.zh-cn.md", "readme.cn.md",  # 双语 README 语言变体（GitHub 标准惯例）
    "license", "license.md", "license.txt",
    ".gitignore",
    "claim_card.html", "claim_card_en.html", "claim_card.json",
    "verify_public.py", "requirements.txt", "setup.py", "pyproject.toml",
    "start.html", "index.html",
}

DOC_EXTS = {".html", ".md", ".pdf", ".pptx"}

# 公开仓内部文档特征（文件名/路径含其一即视为内部机密，禁止进公开仓）
INTERNAL_SIGNS = (
    "复盘", "补齐", "对照", "战略", "投资人", "口径卡",
    "进度追踪", "PRD", "架构", "内部",
)


def _run(args):
    try:
        return subprocess.check_output(args, stderr=subprocess.DEVNULL).decode("utf-8", "replace")
    except Exception:
        return ""


def repo_root():
    return _run(["git", "rev-parse", "--show-toplevel"]).strip()


def staged_files():
    return [f.strip() for f in _run(["git", "diff", "--cached", "--name-only"]).splitlines() if f.strip()]


def is_public_repo(root):
    """公开仓识别：remote url 含 N1Mem-public，或根目录存在 claim_card.json。"""
    url = _run(["git", "remote", "get-url", "origin"]).lower()
    if "n1mem-public" in url:
        return True
    if os.path.exists(os.path.join(root, "claim_card.json")):
        return True
    return False


def is_internal_doc(path):
    """判断文件是否为不应进公开仓的内部文档。"""
    p = path.replace("\\", "/")
    base = os.path.basename(p)
    # docs/_archive/ 整体禁止
    if "/_archive/" in p or p.startswith("_archive/"):
        return True
    for sign in INTERNAL_SIGNS:
        if sign in base:
            return True
    return False


def main():
    root = repo_root()
    if not root:
        return 0  # 非仓库环境不阻挡

    staged = staged_files()

    # ① 根目录散落文档检查（原逻辑，所有仓库）
    bad_root = []
    for f in staged:
        if not f or "/" in f:  # 子目录文件放行
            continue
        base = os.path.basename(f).lower()
        ext = os.path.splitext(base)[1]
        if ext in DOC_EXTS and base not in WHITELIST:
            # README 语言变体（README.zh.md / README.zh-CN.md 等）属 GitHub 标准双语惯例，放行
            if base.startswith("readme.") and ext == ".md":
                continue
            bad_root.append(f)

    # ② 公开仓内部文档检查（仅 N1Mem-public）
    bad_internal = []
    if is_public_repo(root):
        for f in staged:
            if is_internal_doc(f):
                bad_internal.append(f)

    if not bad_root and not bad_internal:
        return 0

    sys.stderr.write("\n[doc-gate] \u2716 提交被拦截，原因如下：\n")
    if bad_root:
        sys.stderr.write(
            "  [A] 仓库根目录禁止散落文档，请归入子目录（如 docs/ 或对应分类）：\n"
        )
        for f in bad_root:
            sys.stderr.write("    - %s\n" % f)
    if bad_internal:
        sys.stderr.write(
            "  [B] 公开仓禁止提交内部文档（含 复盘/补齐/对照/战略/投资人/口径卡/\n"
            "       进度追踪/PRD/架构/内部 字样，或位于 docs/_archive/）：\n"
        )
        for f in bad_internal:
            sys.stderr.write("    - %s\n" % f)
    sys.stderr.write(
        "[doc-gate]   移入正确目录或删除后再提交；紧急绕过: git commit --no-verify\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
