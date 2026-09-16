#!/usr/bin/env python3
"""Behavior tests for validate_artifact.py using temporary artifacts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_artifact import validate_html, validate_markdown


VALID_MARKDOWN = """---
title: 分页注意力
aliases:
  - PagedAttention
tags:
  - tech/inference
type: technical-note
topic: PagedAttention
status: seed
created: 2026-08-25
updated: 2026-08-25
source_quality: high
---
# 分页注意力

## 核心机制

分页注意力使用块映射管理缓存。[S1]

## 来源与证据

- [S1] **论文**｜作者｜原始论文｜2023  
  URL：<https://arxiv.org/abs/2309.06180>  
  检索日期：2026-08-25  
  支撑：块映射机制。
"""


VALID_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<meta name="description" content="测试技术报告">
<title>测试报告</title><style>
.toc{position:fixed;top:0;left:0;width:230px}.toc a{display:block}
main{margin-left:230px}
@media (max-width:1100px){.toc{position:static}main{margin-left:0}}
@media print{.toc{display:none}main{margin-left:0}}
</style></head><body>
<nav class="toc" aria-label="报告目录"><a href="#a">A</a><a href="#b">B</a><a href="#c">C</a></nav>
<main><section id="a"></section><section id="b"></section><section id="c"></section></main>
</body></html>"""


class ValidatorTests(unittest.TestCase):
    def write(self, root: Path, name: str, content: str) -> Path:
        path = root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_valid_markdown_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(Path(tmp), "note.md", VALID_MARKDOWN)
            self.assertEqual([], validate_markdown(path))

    def test_missing_source_definition_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = VALID_MARKDOWN.replace("- [S1] **论文**", "- [S2] **论文**")
            path = self.write(Path(tmp), "note.md", broken)
            errors = validate_markdown(path)
            self.assertTrue(any("没有定义" in item for item in errors))

    def test_valid_html_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(Path(tmp), "report.html", VALID_HTML)
            self.assertEqual([], validate_html(path))

    def test_toc_target_and_external_dependency_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = VALID_HTML.replace('id="c"', 'id="d"').replace(
                "</head>", '<script src="https://cdn.example.test/a.js"></script></head>'
            )
            path = self.write(Path(tmp), "report.html", broken)
            errors = validate_html(path)
            self.assertTrue(any("对应正文 id" in item for item in errors))
            self.assertTrue(any("外部运行依赖" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
