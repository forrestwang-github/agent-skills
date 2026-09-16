#!/usr/bin/env python3
"""Streaming importer for Alibaba Cloud bill exports."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterable, Iterator, List, Optional, Tuple

from bill_models import ImportResult, ValidationIssue
from bill_schema import (
    BillingTypeMapper,
    build_header_mapping,
    clean_text,
    map_row_to_record,
    missing_required_headers,
)


SUPPORTED_SUFFIXES = {".xlsx", ".csv", ".zip"}
MAX_ZIP_ENTRY_SIZE = 512 * 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_files(input_path: Path) -> List[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"不支持的文件类型: {input_path.suffix}")
        return [input_path]
    if not input_path.is_dir():
        raise ValueError(f"输入路径不存在: {input_path}")
    files = [
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    if not files:
        raise ValueError(f"目录中没有可识别的账单文件: {input_path}")
    return sorted(files, key=lambda p: str(p).lower())


class BillFileImporter:
    def __init__(self, mapping_path: Optional[Path] = None):
        self.billing_type_mapper = BillingTypeMapper(mapping_path)
        self._seen_content_hashes: Dict[str, str] = {}

    def load(self, input_path: Path) -> ImportResult:
        result = ImportResult(
            manifest={
                "source": "file",
                "input": str(input_path.resolve()),
                "files": [],
                "raw_row_count": 0,
                "parsed_row_count": 0,
            }
        )
        for path in discover_files(input_path):
            suffix = path.suffix.lower()
            if suffix == ".zip":
                self._load_zip(path, result)
            else:
                content_hash = sha256_file(path)
                if not self._accept_hash(content_hash, str(path), result):
                    continue
                with path.open("rb") as handle:
                    self._load_stream(
                        handle,
                        suffix=suffix,
                        source_name=str(path.resolve()),
                        content_hash=content_hash,
                        result=result,
                    )
        result.manifest["parsed_row_count"] = len(result.records)
        return result

    def _accept_hash(
        self, content_hash: str, source_name: str, result: ImportResult
    ) -> bool:
        previous = self._seen_content_hashes.get(content_hash)
        if previous:
            result.issues.append(
                ValidationIssue(
                    severity="warning",
                    code="DUPLICATE_FILE",
                    message=f"文件内容与已导入文件相同，已跳过: {source_name}",
                    samples=[previous, source_name],
                )
            )
            return False
        self._seen_content_hashes[content_hash] = source_name
        return True

    def _load_zip(self, path: Path, result: ImportResult) -> None:
        container_hash = sha256_file(path)
        try:
            with zipfile.ZipFile(path) as archive:
                entries = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir()
                    and Path(info.filename).suffix.lower() in {".xlsx", ".csv"}
                ]
                if not entries:
                    raise ValueError("ZIP 中没有 XLSX 或 CSV")
                for info in entries:
                    if info.file_size > MAX_ZIP_ENTRY_SIZE:
                        result.issues.append(
                            ValidationIssue(
                                severity="error",
                                code="ZIP_ENTRY_TOO_LARGE",
                                message=f"ZIP 条目过大: {info.filename}",
                            )
                        )
                        continue
                    data = archive.read(info)
                    entry_hash = sha256_bytes(data)
                    source_name = f"{path.resolve()}!{info.filename}"
                    if not self._accept_hash(entry_hash, source_name, result):
                        continue
                    self._load_stream(
                        io.BytesIO(data),
                        suffix=Path(info.filename).suffix.lower(),
                        source_name=source_name,
                        content_hash=entry_hash,
                        result=result,
                        container_hash=container_hash,
                    )
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="ZIP_READ_FAILED",
                    message=f"ZIP 解析失败: {path}: {exc}",
                )
            )

    def _load_stream(
        self,
        handle: BinaryIO,
        *,
        suffix: str,
        source_name: str,
        content_hash: str,
        result: ImportResult,
        container_hash: str = "",
    ) -> None:
        source_manifest: Dict[str, Any] = {
            "name": source_name,
            "sha256": content_hash,
            "container_sha256": container_hash,
            "type": suffix.lstrip("."),
            "sheets": [],
            "raw_row_count": 0,
            "parsed_row_count": 0,
        }
        before = len(result.records)
        try:
            if suffix == ".xlsx":
                self._load_xlsx(
                    handle,
                    source_name,
                    content_hash,
                    result,
                    source_manifest,
                )
            elif suffix == ".csv":
                self._load_csv(
                    handle,
                    source_name,
                    content_hash,
                    result,
                    source_manifest,
                )
            else:
                raise ValueError(f"不支持的文件类型: {suffix}")
        except Exception as exc:
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="FILE_READ_FAILED",
                    message=f"文件解析失败: {source_name}: {exc}",
                )
            )
        source_manifest["parsed_row_count"] = len(result.records) - before
        result.manifest["files"].append(source_manifest)

    def _load_xlsx(
        self,
        handle: BinaryIO,
        source_name: str,
        content_hash: str,
        result: ImportResult,
        source_manifest: Dict[str, Any],
    ) -> None:
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("缺少 openpyxl，无法读取 XLSX") from exc

        workbook = openpyxl.load_workbook(
            handle, read_only=True, data_only=True
        )
        valid_sheet_count = 0
        try:
            for worksheet in workbook.worksheets:
                rows = worksheet.iter_rows(values_only=True)
                header_info = self._find_header(rows)
                if header_info is None:
                    source_manifest["sheets"].append(
                        {
                            "name": worksheet.title,
                            "status": "ignored",
                            "reason": "未识别到计费项明细表头",
                        }
                    )
                    continue
                header_row, headers, mapping = header_info
                valid_sheet_count += 1
                sheet_manifest = {
                    "name": worksheet.title,
                    "status": "parsed",
                    "header_row": header_row,
                    "column_count": len(headers),
                    "field_mapping": mapping,
                    "raw_row_count": 0,
                    "parsed_row_count": 0,
                }
                source_manifest["sheets"].append(sheet_manifest)
                self._consume_rows(
                    rows,
                    headers,
                    mapping,
                    source_name=source_name,
                    content_hash=content_hash,
                    sheet_name=worksheet.title,
                    start_row=header_row + 1,
                    result=result,
                    source_manifest=source_manifest,
                    sheet_manifest=sheet_manifest,
                )
        finally:
            workbook.close()
        if valid_sheet_count == 0:
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="NO_BILL_DETAIL_SHEET",
                    message=f"未找到可识别的计费项明细 Sheet: {source_name}",
                )
            )

    def _find_header(
        self, rows: Iterator[Tuple[Any, ...]], scan_limit: int = 20
    ) -> Optional[Tuple[int, List[str], Dict[str, str]]]:
        for row_number in range(1, scan_limit + 1):
            try:
                row = next(rows)
            except StopIteration:
                return None
            headers = [clean_text(value) for value in row]
            if not any(headers):
                continue
            try:
                mapping = build_header_mapping(headers)
            except ValueError:
                continue
            if not missing_required_headers(mapping):
                return row_number, headers, mapping
        return None

    def _load_csv(
        self,
        handle: BinaryIO,
        source_name: str,
        content_hash: str,
        result: ImportResult,
        source_manifest: Dict[str, Any],
    ) -> None:
        data = handle.read()
        text = None
        encoding = ""
        for candidate in ("utf-8-sig", "gb18030"):
            try:
                text = data.decode(candidate)
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("CSV 编码不是 UTF-8、UTF-8 BOM 或 GB18030")

        reader = csv.reader(io.StringIO(text, newline=""))
        header_info = self._find_header(iter(reader))
        if header_info is None:
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="NO_BILL_DETAIL_HEADER",
                    message=f"CSV 未识别到计费项明细表头: {source_name}",
                )
            )
            return
        header_row, headers, mapping = header_info
        source_manifest["encoding"] = encoding
        sheet_manifest = {
            "name": "CSV",
            "status": "parsed",
            "header_row": header_row,
            "column_count": len(headers),
            "field_mapping": mapping,
            "raw_row_count": 0,
            "parsed_row_count": 0,
        }
        source_manifest["sheets"].append(sheet_manifest)
        self._consume_rows(
            reader,
            headers,
            mapping,
            source_name=source_name,
            content_hash=content_hash,
            sheet_name="CSV",
            start_row=header_row + 1,
            result=result,
            source_manifest=source_manifest,
            sheet_manifest=sheet_manifest,
        )

    def _consume_rows(
        self,
        rows: Iterable[Tuple[Any, ...] | List[Any]],
        headers: List[str],
        mapping: Dict[str, str],
        *,
        source_name: str,
        content_hash: str,
        sheet_name: str,
        start_row: int,
        result: ImportResult,
        source_manifest: Dict[str, Any],
        sheet_manifest: Dict[str, Any],
    ) -> None:
        parsed = 0
        raw_count = 0
        for row_number, values in enumerate(rows, start=start_row):
            values_list = list(values)
            if not any(clean_text(value) for value in values_list):
                continue
            raw_count += 1
            raw = {
                header: values_list[index] if index < len(values_list) else None
                for index, header in enumerate(headers)
                if header
            }
            try:
                record = map_row_to_record(
                    raw,
                    mapping,
                    source_file=source_name,
                    source_file_sha256=content_hash,
                    source_sheet=sheet_name,
                    source_row=row_number,
                    billing_type_mapper=self.billing_type_mapper,
                )
                result.records.append(record)
                parsed += 1
            except Exception as exc:
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="ROW_PARSE_FAILED",
                        message=(
                            f"行解析失败: {source_name} / {sheet_name} / "
                            f"第{row_number}行: {exc}"
                        ),
                        samples=[f"{source_name}:{sheet_name}:{row_number}"],
                    )
                )
        sheet_manifest["raw_row_count"] += raw_count
        sheet_manifest["parsed_row_count"] += parsed
        source_manifest["raw_row_count"] += raw_count
        result.manifest["raw_row_count"] += raw_count
