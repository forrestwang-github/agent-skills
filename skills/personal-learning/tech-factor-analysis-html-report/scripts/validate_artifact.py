#!/usr/bin/env python3
"""Validate Markdown knowledge notes and optional single-file HTML reading copies.

Usage:
    python scripts/validate_artifact.py note.md [report.html ...]

The validator checks structural invariants only. It cannot judge whether an
explanation is correct or whether the cited source actually supports a claim.
"""

from __future__ import annotations

import io
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


REQUIRED_PROPERTIES = {
    "title",
    "tags",
    "type",
    "topic",
    "status",
    "created",
    "updated",
    "source_quality",
}
STATUS_VALUES = {"seed", "growing", "verified"}
SOURCE_QUALITY_VALUES = {"high", "mixed", "limited"}
CONTEXT_RESIDUES = re.compile(
    r"刚刚提到的|你上传的|用户上传的|见附件|见截图|本次对话|终稿|定稿|修订版|整合版"
)
PLACEHOLDERS = re.compile(r"YYYY-MM-DD|example\.com|\bTODO\b|待补充来源|在此填写")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def strip_fenced_code(text: str) -> str:
    return re.sub(r"```.*?```|~~~.*?~~~", "", text, flags=re.S)


def parse_simple_frontmatter(text: str) -> Tuple[Dict[str, str], str, List[str]]:
    errors: List[str] = []
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.S)
    if not match:
        return {}, text, ["文件开头缺少完整 YAML frontmatter"]

    raw = match.group(1)
    props: Dict[str, str] = {}
    for line_no, line in enumerate(raw.splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        item = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if not item:
            errors.append(f"frontmatter 第 {line_no} 行不是可识别的扁平属性")
            continue
        key, value = item.group(1), item.group(2).strip().strip('"\'')
        if key in props:
            errors.append(f"frontmatter 属性重复：{key}")
        props[key] = value
    return props, text[match.end() :], errors


def validate_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_markdown(path: Path) -> List[str]:
    text = read_text(path)
    props, body, errors = parse_simple_frontmatter(text)

    missing = sorted(REQUIRED_PROPERTIES - props.keys())
    if missing:
        errors.append("缺少必需属性：" + ", ".join(missing))

    if props.get("status") and props["status"] not in STATUS_VALUES:
        errors.append("status 必须是 seed、growing 或 verified")
    if props.get("source_quality") and props["source_quality"] not in SOURCE_QUALITY_VALUES:
        errors.append("source_quality 必须是 high、mixed 或 limited")
    for field in ("created", "updated"):
        if props.get(field) and not validate_iso_date(props[field]):
            errors.append(f"{field} 必须是有效的 ISO 日期 YYYY-MM-DD")

    plain_body = strip_fenced_code(body)
    h1s = re.findall(r"(?m)^#\s+(.+?)\s*$", plain_body)
    if len(h1s) != 1:
        errors.append(f"正文必须且只能有一个 H1（当前 {len(h1s)} 个）")
    elif props.get("title") and h1s[0].strip() != props["title"].strip():
        errors.append("H1 与 frontmatter 的 title 不一致")

    references = set(re.findall(r"\[S(\d+)\]", plain_body))
    definitions = set(re.findall(r"(?m)^\s*-?\s*\[S(\d+)\]\s+", plain_body))
    if not references:
        errors.append("正文没有 [S1] 形式的来源标记")
    if references and not definitions:
        errors.append("存在来源标记，但文末没有来源定义")
    missing_definitions = sorted(references - definitions, key=int)
    if missing_definitions:
        errors.append("以下来源标记没有定义：" + ", ".join("S" + n for n in missing_definitions))
    unused_definitions = sorted(definitions - references, key=int)
    if unused_definitions:
        errors.append("以下来源定义没有被正文引用：" + ", ".join("S" + n for n in unused_definitions))

    url_count = len(re.findall(r"https?://[^\s)>]+", plain_body))
    support_count = len(re.findall(r"(?m)^\s*支撑[：:]", plain_body))
    if definitions and url_count < len(definitions):
        errors.append("每条来源定义至少需要一个可核验 URL")
    if definitions and support_count < len(definitions):
        errors.append("每条来源定义需要说明“支撑：”的具体声明")

    residue = CONTEXT_RESIDUES.search(plain_body)
    if residue:
        errors.append(f"发现对话或版本性残留：{residue.group(0)}")
    placeholder = PLACEHOLDERS.search(text)
    if placeholder:
        errors.append(f"发现未替换占位内容：{placeholder.group(0)}")

    return errors


class ReportHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.toc_nesting = 0
        self.toc_count = 0
        self.toc_links: List[str] = []
        self.ids: List[str] = []
        self.styles: List[str] = []
        self._in_style = False
        self._style_parts: List[str] = []
        self.html_lang = ""
        self.has_charset = False
        self.has_viewport = False
        self.has_description = False
        self.has_title = False
        self._in_title = False
        self.external_dependencies: List[str] = []

    @staticmethod
    def attrs_dict(attrs: Sequence[Tuple[str, str | None]]) -> Dict[str, str]:
        return {key.lower(): value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = self.attrs_dict(attrs)

        if tag == "html":
            self.html_lang = data.get("lang", "")
        if tag == "meta":
            if data.get("charset", "").lower() == "utf-8":
                self.has_charset = True
            if data.get("name", "").lower() == "viewport":
                self.has_viewport = True
            if data.get("name", "").lower() == "description" and data.get("content", "").strip():
                self.has_description = True
        if tag == "title":
            self._in_title = True
        if tag == "style":
            self._in_style = True
            self._style_parts = []

        element_id = data.get("id", "")
        if element_id:
            self.ids.append(element_id)

        classes = set(data.get("class", "").split())
        is_toc = tag == "nav" and ("toc" in classes or element_id == "toc")
        if is_toc:
            self.toc_count += 1
            self.toc_nesting = 1
        elif self.toc_nesting and tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.toc_nesting += 1

        if self.toc_nesting and tag == "a":
            href = data.get("href", "")
            if href.startswith("#") and len(href) > 1:
                self.toc_links.append(href[1:])

        if tag == "link" and "stylesheet" in data.get("rel", "").lower().split():
            self.external_dependencies.append(data.get("href", "<missing href>"))
        if tag == "script" and data.get("src"):
            self.external_dependencies.append(data["src"])
        if tag in {"img", "audio", "video", "iframe"}:
            src = data.get("src", "")
            if src and not (src.startswith("data:") or src.startswith("#")):
                self.external_dependencies.append(src)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "style" and self._in_style:
            self.styles.append("".join(self._style_parts))
            self._in_style = False
            self._style_parts = []
        if tag == "title":
            self._in_title = False
        if self.toc_nesting:
            self.toc_nesting -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_parts.append(data)
        if self._in_title and data.strip():
            self.has_title = True


def compact_css(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"\s+", "", text).lower()


def find_css_rule(css: str, selector: str) -> List[str]:
    rules: List[str] = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css, flags=re.S):
        if selector in [item.strip() for item in selectors.split(",")]:
            rules.append(body)
    return rules


def extract_media_blocks(css: str, media_pattern: str) -> List[str]:
    blocks: List[str] = []
    for match in re.finditer(media_pattern, css, flags=re.I):
        opening = css.find("{", match.end())
        if opening < 0:
            continue
        depth = 0
        for index in range(opening, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(css[opening + 1 : index])
                    break
    return blocks


def property_is_zero(rule: str, name: str) -> bool:
    match = re.search(rf"(?:^|;)\s*{re.escape(name)}\s*:\s*([^;}}]+)", rule, flags=re.I)
    if not match:
        return False
    return bool(re.fullmatch(r"0(?:px|rem|em|%)?", match.group(1).strip(), flags=re.I))


def validate_html(path: Path) -> List[str]:
    text = read_text(path)
    parser = ReportHTMLParser()
    try:
        parser.feed(text)
    except Exception as exc:  # HTMLParser rarely raises, but return a useful failure if it does.
        return [f"HTML 无法解析：{exc}"]

    errors: List[str] = []
    if parser.html_lang.lower() not in {"zh-cn", "zh-hans"}:
        errors.append("<html> 缺少 lang=\"zh-CN\" 或等价简体中文标记")
    if not parser.has_charset:
        errors.append("缺少 UTF-8 charset 元信息")
    if not parser.has_viewport:
        errors.append("缺少 viewport 元信息")
    if not parser.has_description:
        errors.append("缺少非空 description 元信息")
    if not parser.has_title:
        errors.append("缺少非空 <title>")
    if parser.toc_count != 1:
        errors.append(f"必须且只能有一个 nav.toc（当前 {parser.toc_count} 个）")
    if len(parser.toc_links) < 3:
        errors.append(f"目录内锚点链接少于 3 个（当前 {len(parser.toc_links)} 个）")
    if len(parser.toc_links) != len(set(parser.toc_links)):
        errors.append("目录含重复锚点链接")

    duplicate_ids = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    if duplicate_ids:
        errors.append("HTML 含重复 id：" + ", ".join(duplicate_ids))
    missing_targets = sorted(set(parser.toc_links) - set(parser.ids))
    if missing_targets:
        errors.append("目录链接没有对应正文 id：" + ", ".join(missing_targets))

    css = "\n".join(parser.styles)
    toc_rules = find_css_rule(css, ".toc")
    fixed_rules = [rule for rule in toc_rules if "position:fixed" in compact_css(rule)]
    if not fixed_rules:
        errors.append("基础 .toc 样式缺少 position: fixed")
    elif not any(property_is_zero(rule, "top") and property_is_zero(rule, "left") for rule in fixed_rules):
        errors.append("固定目录必须同时使用 top: 0 和 left: 0")

    main_rules = find_css_rule(css, "main")
    if not any(re.search(r"margin-left\s*:\s*(?!0(?:\D|$))", rule, flags=re.I) for rule in main_rules):
        errors.append("桌面正文 main 缺少非零 margin-left，可能被目录遮挡")

    print_blocks = extract_media_blocks(css, r"@media\s+print\b")
    if not any(
        any("display:none" in compact_css(rule) for rule in find_css_rule(block, ".toc"))
        for block in print_blocks
    ):
        errors.append("@media print 中没有隐藏 .toc")

    responsive_blocks = extract_media_blocks(css, r"@media\s*\([^)]*max-width[^)]*\)")
    if not any(
        any("position:static" in compact_css(rule) for rule in find_css_rule(block, ".toc"))
        and any("margin-left:0" in compact_css(rule) for rule in find_css_rule(block, "main"))
        for block in responsive_blocks
    ):
        errors.append("缺少窄屏目录降级和 main 取消左侧避让规则")

    if parser.external_dependencies:
        errors.append("发现外部运行依赖：" + ", ".join(parser.external_dependencies))
    if re.search(r"\b(?:localStorage|sessionStorage)\b", text):
        errors.append("HTML 不得使用 localStorage 或 sessionStorage")
    placeholder = PLACEHOLDERS.search(text)
    if placeholder:
        errors.append(f"发现未替换占位内容：{placeholder.group(0)}")

    return errors


def validate_path(path: Path) -> List[str]:
    if not path.exists():
        return ["文件不存在"]
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return validate_markdown(path)
    if suffix in {".html", ".htm"}:
        return validate_html(path)
    return ["只支持 .md、.markdown、.html 或 .htm 文件"]


def write_lines(lines: Iterable[str], stream: io.TextIOBase) -> None:
    for line in lines:
        stream.write(line + "\n")
    stream.flush()


def main(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        write_lines(["用法: python scripts/validate_artifact.py <笔记.md> [报告.html ...]"], sys.stderr)
        return 2

    failures = 0
    output: List[str] = []
    for raw_path in argv[1:]:
        path = Path(raw_path)
        errors = validate_path(path)
        if errors:
            failures += 1
            output.append(f"[FAIL] {path}（{len(errors)} 项）")
            output.extend(f"  {index}. {message}" for index, message in enumerate(errors, 1))
        else:
            output.append(f"[OK] {path}")

    stream = sys.stderr if failures else sys.stdout
    if hasattr(stream, "buffer"):
        stream = io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace", write_through=True)
    write_lines(output, stream)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
