#!/usr/bin/env python3
"""Deterministic manager for a versioned multi-skill repository."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(r"E:\AI Workspace\skills")
REGISTRY_DIR = "registry"
CATALOG_FILE = Path(REGISTRY_DIR) / "catalog.json"
REPOSITORY_FILE = Path(REGISTRY_DIR) / "repository.json"
SKILLS_DIR = "skills"
LICENSE_FILE = "LICENSE"
EXPECTED_LICENSE = "Apache-2.0"
README_START = "<!-- skill-catalog:start -->"
README_END = "<!-- skill-catalog:end -->"
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.S)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
REF_RE = re.compile(r"\]\((references/[^)#]+)(?:#[^)]+)?\)")


class SkillCtlError(RuntimeError):
    pass


def emit(payload: dict[str, Any], as_json: bool, exit_code: int = 0) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("message") or json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SkillCtlError(f"Command failed ({' '.join(cmd)}): {detail}")
    return result


def find_repo_root(value: str | None) -> Path:
    if value:
        root = Path(value).expanduser().resolve()
    else:
        candidates = [Path.cwd(), *Path(__file__).resolve().parents, DEFAULT_REPO_ROOT]
        root = next((p for p in candidates if (p / CATALOG_FILE).is_file()), DEFAULT_REPO_ROOT)
        root = root.resolve()
    if not root.is_dir():
        raise SkillCtlError(f"Repository root not found: {root}")
    return root


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise SkillCtlError(f"Required file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillCtlError(f"Invalid JSON file {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def catalog(root: Path) -> dict[str, Any]:
    data = load_json(root / CATALOG_FILE)
    if data.get("schema_version") != 1 or not isinstance(data.get("skills"), list):
        raise SkillCtlError("Unsupported catalog.json schema")
    return data


def catalog_entry(root: Path, name: str) -> dict[str, Any]:
    for entry in catalog(root)["skills"]:
        if entry.get("name") == name:
            return entry
    raise SkillCtlError(f"Skill is not listed in catalog.json: {name}")


def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise SkillCtlError("SKILL.md has no valid YAML frontmatter block")
    values: dict[str, str] = {}
    for raw in match.group(1).splitlines():
        if not raw or raw[0].isspace() or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def catalog_sort_key(entry: dict[str, Any]) -> tuple[int, str, str]:
    path = Path(str(entry.get("path", "")))
    category = path.parts[1] if len(path.parts) >= 3 else ""
    category_order = {"tooling": 0, "work": 1, "personal-learning": 2}
    name = str(entry.get("name", ""))
    manager_order = "0" if name == "skill-repository-manager" else "1"
    return category_order.get(category, 99), category, manager_order + name


def render_readme_catalog(data: dict[str, Any]) -> str:
    repository = str(data.get("repository", "")).strip()
    entries = sorted(data["skills"], key=catalog_sort_key)
    category_counts: dict[str, int] = {}
    for entry in entries:
        parts = Path(str(entry.get("path", ""))).parts
        category = parts[1] if len(parts) >= 3 else ""
        category_counts[category] = category_counts.get(category, 0) + 1
    category_labels = {
        "tooling": "工具（tooling）",
        "work": "工作（work）",
        "personal-learning": "个人学习（personal-learning）",
    }
    lines = [
        README_START,
        "<table>",
        "  <thead>",
        "    <tr><th>分类</th><th>Skill</th><th>最新稳定版</th><th>安装</th><th>用途</th></tr>",
        "  </thead>",
        "  <tbody>",
    ]
    rendered_categories: set[str] = set()
    for entry in entries:
        name = str(entry["name"])
        path = str(entry["path"]).replace("\\", "/")
        parts = Path(path).parts
        category = parts[1] if len(parts) >= 3 else ""
        description = html.escape(" ".join(str(entry.get("description", "")).split()))
        version = str(entry.get("version", ""))
        release_tag = entry.get("release_tag")
        if release_tag and repository:
            tag = str(release_tag)
            version_cell = f'<a href="https://github.com/{repository}/releases/tag/{tag}"><code>v{html.escape(version)}</code></a>'
            install_cell = f'<a href="https://github.com/{repository}/tree/{tag}/{path}">固定版本</a>'
        else:
            version_cell = "未正式发布"
            install_cell = f'<a href="{path}/">查看 main</a>'
        lines.append("    <tr>")
        if category not in rendered_categories:
            category_label = category_labels.get(category, category)
            lines.append(
                f'      <td rowspan="{category_counts[category]}">{html.escape(category_label)}</td>'
            )
            rendered_categories.add(category)
        lines.extend([
            f'      <td><a href="{path}/"><code>{html.escape(name)}</code></a></td>',
            f"      <td>{version_cell}</td>",
            f"      <td>{install_cell}</td>",
            f"      <td>{description}</td>",
            "    </tr>",
        ])
    lines.extend(["  </tbody>", "</table>", README_END])
    return "\n".join(lines)


def replace_readme_catalog(text: str, data: dict[str, Any]) -> str:
    start = text.find(README_START)
    end = text.find(README_END)
    if start < 0 or end < 0 or end < start:
        raise SkillCtlError("README.md is missing valid skill catalog markers")
    end += len(README_END)
    return text[:start] + render_readme_catalog(data) + text[end:]


def sync_readme_catalog(root: Path, data: dict[str, Any]) -> bool:
    path = root / "README.md"
    current = path.read_text(encoding="utf-8")
    updated = replace_readme_catalog(current, data)
    if updated == current:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    data = catalog(root)
    entries = data["skills"]
    names = [str(item.get("name", "")) for item in entries]
    paths = [str(item.get("path", "")).replace("\\", "/") for item in entries]
    if len(names) != len(set(names)):
        errors.append("Catalog contains duplicate skill names")
    if len(paths) != len(set(paths)):
        errors.append("Catalog contains duplicate skill paths")
    listed = set(paths)
    discovered = {
        path.parent.relative_to(root).as_posix()
        for path in (root / SKILLS_DIR).glob("*/*/SKILL.md")
    }
    for path in sorted(discovered - listed):
        errors.append(f"Unregistered skill directory: {path}")
    for path in sorted(listed - discovered):
        errors.append(f"Catalog path has no SKILL.md: {path}")
    readme_path = root / "README.md"
    if not readme_path.is_file():
        errors.append("README.md not found")
    else:
        current = readme_path.read_text(encoding="utf-8")
        try:
            expected = replace_readme_catalog(current, data)
            if expected != current:
                errors.append("README skill catalog is out of sync with registry/catalog.json")
        except SkillCtlError as exc:
            errors.append(str(exc))
    return errors


def validate_skill(root: Path, name: str) -> dict[str, Any]:
    entry = catalog_entry(root, name)
    skill_dir = (root / entry.get("path", name)).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    skills_root = (root / SKILLS_DIR).resolve()
    try:
        relative_skill = skill_dir.relative_to(skills_root)
    except ValueError:
        relative_skill = Path()
        errors.append(f"Skill path must be inside repository {SKILLS_DIR}/ directory")
    if relative_skill.parts and (len(relative_skill.parts) != 2 or relative_skill.name != name):
        errors.append(f"Skill path must use {SKILLS_DIR}/<category>/{name}")
    repository = load_json(root / REPOSITORY_FILE)
    if repository.get("license") != EXPECTED_LICENSE:
        errors.append(f"Repository license must be {EXPECTED_LICENSE}")
    root_license = root / LICENSE_FILE
    skill_license = skill_dir / LICENSE_FILE
    if not root_license.is_file():
        errors.append(f"Repository {LICENSE_FILE} not found")
    if not skill_license.is_file():
        errors.append(f"Skill {LICENSE_FILE} not found")
    elif root_license.is_file() and file_hash(root_license) != file_hash(skill_license):
        errors.append(f"Skill {LICENSE_FILE} does not match repository {LICENSE_FILE}")
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        errors.append("SKILL.md not found")
        return {"name": name, "path": str(skill_dir), "valid": False, "errors": errors, "warnings": warnings}
    try:
        metadata = parse_frontmatter(skill_md)
    except (OSError, UnicodeDecodeError, SkillCtlError) as exc:
        errors.append(str(exc))
        metadata = {}
    actual_name = metadata.get("name", "")
    if actual_name != name:
        errors.append(f"Frontmatter name '{actual_name}' does not match catalog name '{name}'")
    if not NAME_RE.fullmatch(actual_name):
        errors.append("Skill name is not lowercase hyphen-case")
    if not metadata.get("description"):
        errors.append("Frontmatter description is missing")
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if "\ufffd" in text:
        errors.append("SKILL.md is not valid UTF-8")
    if re.search(r"^\s*\[TODO:[^\]]*\]\s*$", text, re.M):
        errors.append("Unfinished TODO placeholder found")
    for rel in REF_RE.findall(text):
        if not (skill_dir / rel).is_file():
            errors.append(f"Missing referenced file: {rel}")
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if openai_yaml.exists():
        yaml_text = openai_yaml.read_text(encoding="utf-8", errors="replace")
        if "interface:" not in yaml_text or "default_prompt:" not in yaml_text:
            warnings.append("agents/openai.yaml lacks interface or default_prompt")
        if f"${name}" not in yaml_text:
            warnings.append("default_prompt does not mention the skill explicitly")
    version = str(entry.get("version", ""))
    if not SEMVER_RE.fullmatch(version):
        errors.append(f"Catalog version is not semantic: {version}")
    return {"name": name, "path": str(skill_dir), "version": version, "valid": not errors, "errors": errors, "warnings": warnings}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(bytes.fromhex(file_hash(path)))
    return digest.hexdigest()


def local_config(root: Path) -> dict[str, Any]:
    return load_json(root / ".skillctl.local.json", default={})


def destination(root: Path, agent: str | None, dest: str | None) -> Path:
    if dest:
        result = Path(dest).expanduser().resolve()
    elif agent == "codex":
        configured = local_config(root).get("agents", {}).get("codex", {}).get("skills_root")
        codex_home = os.environ.get("CODEX_HOME")
        result = Path(configured or (Path(codex_home) / "skills" if codex_home else Path.home() / ".codex" / "skills"))
        result = result.expanduser().resolve()
    else:
        raise SkillCtlError("Specify --agent codex or --dest <absolute path>")
    if not result.is_absolute():
        raise SkillCtlError("Destination must be an absolute path")
    return result


def lock_path(dest_root: Path) -> Path:
    return dest_root / ".managed-skills.json"


def load_lock(dest_root: Path) -> dict[str, Any]:
    return load_json(lock_path(dest_root), default={"schema_version": 1, "skills": {}})


def save_lock(dest_root: Path, data: dict[str, Any]) -> None:
    write_json(lock_path(dest_root), data)


def is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return path.exists() and path.resolve() != path.absolute()
    except OSError:
        return False


def backup_existing(dest_root: Path, name: str, lock_entry: dict[str, Any] | None = None) -> Path | None:
    target = dest_root / name
    if not target.exists() and not target.is_symlink():
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = dest_root / ".skillctl" / "backups" / name / stamp
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(backup))
    write_json(backup.parent / f"{backup.name}.metadata.json", {"lock_entry": lock_entry})
    return backup


def copy_skill(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise SkillCtlError(f"Target already exists: {target}")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def command_verify(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    names = [entry["name"] for entry in catalog(root)["skills"]] if args.all else [args.skill]
    if not names or names == [None]:
        raise SkillCtlError("Specify a skill name or --all")
    results = [validate_skill(root, name) for name in names]
    repository_errors = validate_repository(root)
    return {"ok": all(item["valid"] for item in results) and not repository_errors, "operation": "verify", "repository_errors": repository_errors, "results": results}


def command_register(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if not NAME_RE.fullmatch(args.skill):
        raise SkillCtlError("Skill name must be lowercase hyphen-case")
    if not NAME_RE.fullmatch(args.category):
        raise SkillCtlError("Category must be lowercase hyphen-case")
    if not SEMVER_RE.fullmatch(args.version):
        raise SkillCtlError("Version must use MAJOR.MINOR.PATCH")
    data = catalog(root)
    if any(item.get("name") == args.skill for item in data["skills"]):
        raise SkillCtlError(f"Skill is already registered: {args.skill}")
    relative_path = f"{SKILLS_DIR}/{args.category}/{args.skill}"
    if any(str(item.get("path", "")).replace("\\", "/") == relative_path for item in data["skills"]):
        raise SkillCtlError(f"Skill path is already registered: {relative_path}")
    skill_dir = root / relative_path
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SkillCtlError(f"SKILL.md not found: {skill_md}")
    metadata = parse_frontmatter(skill_md)
    if metadata.get("name") != args.skill:
        raise SkillCtlError(f"Frontmatter name must be {args.skill}")
    description = args.description or metadata.get("description", "")
    if not description:
        raise SkillCtlError("Skill description is missing")
    root_license = root / LICENSE_FILE
    if not root_license.is_file():
        raise SkillCtlError(f"Repository {LICENSE_FILE} not found")
    skill_license = skill_dir / LICENSE_FILE
    if not skill_license.exists():
        license_action = "create"
    elif file_hash(skill_license) != file_hash(root_license):
        license_action = "replace"
    else:
        license_action = "unchanged"
    plan = {"operation": "register", "skill": args.skill, "category": args.category, "path": relative_path, "version": args.version, "description": description, "license_action": license_action, "readme_update": True}
    if not args.yes:
        return {"ok": True, "preview": True, **plan}
    original_catalog = (root / CATALOG_FILE).read_bytes()
    original_readme = (root / "README.md").read_bytes()
    original_license = skill_license.read_bytes() if skill_license.exists() else None
    try:
        shutil.copy2(root_license, skill_license)
        data["skills"].append({"name": args.skill, "path": relative_path, "version": args.version, "release_tag": None, "description": description})
        data["skills"].sort(key=catalog_sort_key)
        write_json(root / CATALOG_FILE, data)
        sync_readme_catalog(root, data)
        verification = command_verify(argparse.Namespace(all=True, skill=None), root)
        if not verification["ok"]:
            raise SkillCtlError(f"Post-registration validation failed: {verification}")
    except Exception:
        (root / CATALOG_FILE).write_bytes(original_catalog)
        (root / "README.md").write_bytes(original_readme)
        if original_license is None:
            skill_license.unlink(missing_ok=True)
        else:
            skill_license.write_bytes(original_license)
        raise
    return {"ok": True, "preview": False, **plan, "verified": True}


def command_sync(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    data = catalog(root)
    root_license = root / LICENSE_FILE
    if not root_license.is_file():
        raise SkillCtlError(f"Repository {LICENSE_FILE} not found")
    license_updates: list[str] = []
    for entry in data["skills"]:
        skill_license = root / entry["path"] / LICENSE_FILE
        if not skill_license.is_file() or file_hash(skill_license) != file_hash(root_license):
            license_updates.append(str(entry["name"]))
    readme = (root / "README.md").read_text(encoding="utf-8")
    readme_update = replace_readme_catalog(readme, data) != readme
    plan = {"operation": "sync", "license_updates": license_updates, "readme_update": readme_update}
    if not args.yes:
        return {"ok": True, "preview": True, **plan}
    for entry in data["skills"]:
        shutil.copy2(root_license, root / entry["path"] / LICENSE_FILE)
    sync_readme_catalog(root, data)
    verification = command_verify(argparse.Namespace(all=True, skill=None), root)
    if not verification["ok"]:
        raise SkillCtlError(f"Post-sync validation failed: {verification}")
    return {"ok": True, "preview": False, **plan, "verified": True}


def command_status(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    dest_root = destination(root, args.agent, args.dest)
    target = dest_root / args.skill
    entry = catalog_entry(root, args.skill)
    lock = load_lock(dest_root).get("skills", {}).get(args.skill)
    exists = target.exists() or target.is_symlink()
    linked_to = str(target.resolve()) if is_link_like(target) else None
    digest = tree_digest(target) if exists and target.is_dir() else None
    modified = bool(lock and digest and lock.get("content_sha256") != digest)
    return {"ok": True, "operation": "status", "skill": args.skill, "source_version": entry["version"], "destination": str(target), "installed": exists, "linked_to": linked_to, "installed_version": lock.get("installed_version") if lock else None, "local_changes": modified}


def command_diff(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    dest_root = destination(root, args.agent, args.dest)
    source = root / catalog_entry(root, args.skill).get("path", args.skill)
    target = dest_root / args.skill
    if not target.is_dir():
        raise SkillCtlError(f"Installed skill not found: {target}")
    source_files = {p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()}
    target_files = {p.relative_to(target).as_posix(): p for p in target.rglob("*") if p.is_file()}
    added = sorted(source_files.keys() - target_files.keys())
    removed = sorted(target_files.keys() - source_files.keys())
    changed = sorted(k for k in source_files.keys() & target_files.keys() if file_hash(source_files[k]) != file_hash(target_files[k]))
    return {"ok": True, "operation": "diff", "skill": args.skill, "source_only": added, "installed_only": removed, "changed": changed}


def command_link(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    dest_root = destination(root, args.agent, args.dest)
    source = (root / catalog_entry(root, args.skill).get("path", args.skill)).resolve()
    target = dest_root / args.skill
    plan = {"operation": "link", "skill": args.skill, "source": str(source), "target": str(target), "replace": args.replace}
    if not args.yes:
        return {"ok": True, "preview": True, **plan}
    dest_root.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists() or is_link_like(target):
        if not args.replace:
            raise SkillCtlError("Target exists; preview with --replace, then confirm")
        existing_lock = load_lock(dest_root).get("skills", {}).get(args.skill)
        backup = backup_existing(dest_root, args.skill, existing_lock)
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        if os.name == "nt":
            junction = run(["cmd", "/c", "mklink", "/J", str(target), str(source)], check=False)
            if junction.returncode != 0:
                if backup and not target.exists():
                    shutil.move(str(backup), str(target))
                detail = (junction.stderr or junction.stdout).strip()
                raise SkillCtlError(f"Unable to create directory link or junction: {exc}; {detail}") from exc
        else:
            if backup and not target.exists():
                shutil.move(str(backup), str(target))
            raise SkillCtlError(f"Unable to create directory link: {exc}") from exc
    return {"ok": True, "preview": False, **plan, "backup": str(backup) if backup else None, "verified_target": str(target.resolve())}


def resolve_remote_catalog(repo: str) -> dict[str, Any]:
    result = run(["gh", "api", f"repos/{repo}/contents/{CATALOG_FILE.as_posix()}", "--jq", ".content"])
    try:
        return json.loads(base64.b64decode(result.stdout.strip()).decode("utf-8"))
    except Exception as exc:
        raise SkillCtlError(f"Unable to decode remote catalog: {exc}") from exc


def remote_entry(root: Path, name: str) -> dict[str, Any]:
    repo = load_json(root / REPOSITORY_FILE)["github_repository"]
    for entry in resolve_remote_catalog(repo).get("skills", []):
        if entry.get("name") == name:
            return entry
    raise SkillCtlError(f"Remote catalog does not list skill: {name}")


def command_check(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    remote = remote_entry(root, args.skill)
    status_args = argparse.Namespace(skill=args.skill, agent=args.agent, dest=args.dest)
    current = command_status(status_args, root)
    return {"ok": True, "operation": "check", "skill": args.skill, "installed_version": current.get("installed_version"), "latest_version": remote.get("version"), "release_tag": remote.get("release_tag"), "update_available": current.get("installed_version") != remote.get("version")}


def materialize_source(root: Path, name: str, source_kind: str, ref: str | None) -> tuple[Path, tempfile.TemporaryDirectory[str] | None, dict[str, Any]]:
    entry = catalog_entry(root, name) if source_kind == "local" else remote_entry(root, name)
    if source_kind == "local":
        return root / entry.get("path", name), None, entry
    repo_info = load_json(root / REPOSITORY_FILE)
    repo = repo_info["github_repository"]
    selected_ref = ref or entry.get("release_tag")
    if not selected_ref:
        raise SkillCtlError("Remote catalog has no release tag")
    temp = tempfile.TemporaryDirectory(prefix="skillctl-")
    clone_root = Path(temp.name) / "repo"
    run(["git", "clone", "--depth", "1", "--branch", selected_ref, f"https://github.com/{repo}.git", str(clone_root)])
    return clone_root / entry.get("path", name), temp, entry


def install_or_update(args: argparse.Namespace, root: Path, updating: bool) -> dict[str, Any]:
    dest_root = destination(root, args.agent, args.dest)
    target = dest_root / args.skill
    operation = "update" if updating else "install"
    source, temp, entry = materialize_source(root, args.skill, args.source, args.ref)
    try:
        verification = validate_skill(root, args.skill) if args.source == "local" else {"valid": (source / "SKILL.md").is_file(), "errors": []}
        if not verification["valid"]:
            raise SkillCtlError(f"Source skill validation failed: {verification['errors']}")
        preview = {"operation": operation, "skill": args.skill, "source": args.source, "version": entry.get("version"), "target": str(target), "will_replace": target.exists() or is_link_like(target)}
        if not args.yes:
            return {"ok": True, "preview": True, **preview}
        dest_root.mkdir(parents=True, exist_ok=True)
        lock = load_lock(dest_root)
        existing_lock = lock.get("skills", {}).get(args.skill)
        if updating and not (target.exists() or is_link_like(target)):
            raise SkillCtlError("Cannot update a skill that is not installed")
        if not updating and (target.exists() or is_link_like(target)):
            raise SkillCtlError("Target exists; use update instead of install")
        if updating and existing_lock and target.is_dir() and not is_link_like(target):
            current_digest = tree_digest(target)
            if current_digest != existing_lock.get("content_sha256") and not args.force:
                raise SkillCtlError("Installed skill has local changes; update refused without --force")
        backup = backup_existing(dest_root, args.skill, existing_lock) if updating else None
        try:
            copy_skill(source, target)
        except Exception:
            if backup and not target.exists():
                shutil.move(str(backup), str(target))
            raise
        installed_digest = tree_digest(target)
        lock.setdefault("skills", {})[args.skill] = {"repository": load_json(root / REPOSITORY_FILE)["github_repository"], "path": entry.get("path", args.skill), "installed_version": entry.get("version"), "installed_ref": args.ref or entry.get("release_tag") or "local", "content_sha256": installed_digest, "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "source": args.source}
        save_lock(dest_root, lock)
        return {"ok": True, "preview": False, **preview, "backup": str(backup) if backup else None, "content_sha256": installed_digest}
    finally:
        if temp:
            temp.cleanup()


def command_rollback(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    dest_root = destination(root, args.agent, args.dest)
    backup_root = dest_root / ".skillctl" / "backups" / args.skill
    backups = sorted((p for p in backup_root.iterdir() if p.is_dir()), reverse=True) if backup_root.is_dir() else []
    if not backups:
        raise SkillCtlError("No managed backup is available")
    selected = backups[0]
    target = dest_root / args.skill
    if not args.yes:
        return {"ok": True, "preview": True, "operation": "rollback", "skill": args.skill, "backup": str(selected), "target": str(target)}
    lock = load_lock(dest_root)
    current_lock = lock.get("skills", {}).get(args.skill)
    displaced = backup_existing(dest_root, args.skill, current_lock) if target.exists() or is_link_like(target) else None
    shutil.move(str(selected), str(target))
    metadata_path = selected.parent / f"{selected.name}.metadata.json"
    restored_metadata = load_json(metadata_path, default={})
    restored_lock = restored_metadata.get("lock_entry")
    if restored_lock:
        lock.setdefault("skills", {})[args.skill] = restored_lock
    else:
        lock.get("skills", {}).pop(args.skill, None)
    save_lock(dest_root, lock)
    return {"ok": True, "preview": False, "operation": "rollback", "skill": args.skill, "restored": str(target), "displaced": str(displaced) if displaced else None}


def bump_version(version: str, bump: str | None, explicit: str | None) -> str:
    if explicit:
        if not SEMVER_RE.fullmatch(explicit):
            raise SkillCtlError("--version must use MAJOR.MINOR.PATCH")
        return explicit
    if not bump:
        raise SkillCtlError("Specify --bump patch|minor|major or --version")
    major, minor, patch = map(int, version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def git_changes(root: Path) -> list[str]:
    result = run(["git", "status", "--porcelain"], cwd=root)
    return [line[3:].replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def validate_release_assets(tag: str, assets: list[dict[str, Any]]) -> dict[str, str]:
    expected = {f"{tag}.zip", f"{tag}.sha256"}
    uploaded = {
        str(asset.get("name")): str(asset.get("url", ""))
        for asset in assets
        if asset.get("state") == "uploaded" and asset.get("url")
    }
    missing = sorted(expected - uploaded.keys())
    if missing:
        raise SkillCtlError(f"Release assets are incomplete: {missing}")
    return {name: uploaded[name] for name in sorted(expected)}


def command_verify_release(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    entry = catalog_entry(root, args.skill)
    tag = args.tag or entry.get("release_tag")
    if not tag:
        raise SkillCtlError(f"No release tag is recorded for {args.skill}")
    expected_prefix = f"{args.skill}-v"
    if not str(tag).startswith(expected_prefix):
        raise SkillCtlError(f"Release tag does not match skill: {tag}")
    repo = load_json(root / REPOSITORY_FILE)["github_repository"]
    deadline = time.monotonic() + max(0, args.wait_seconds)
    workflow: dict[str, Any] | None = None
    while True:
        runs = json.loads(
            run([
                "gh", "run", "list", "--repo", repo, "--workflow", "release-skill.yml",
                "--limit", "30", "--json", "databaseId,headBranch,status,conclusion,url",
            ]).stdout
        )
        workflow = next((item for item in runs if item.get("headBranch") == tag), None)
        if workflow and workflow.get("status") == "completed":
            break
        if time.monotonic() >= deadline:
            state = workflow.get("status") if workflow else "not-found"
            raise SkillCtlError(f"Timed out waiting for release workflow ({state}): {tag}")
        time.sleep(min(5, max(0.1, deadline - time.monotonic())))
    if workflow.get("conclusion") != "success":
        raise SkillCtlError(
            f"Release workflow did not succeed ({workflow.get('conclusion')}): {workflow.get('url')}"
        )
    release = json.loads(
        run([
            "gh", "release", "view", str(tag), "--repo", repo,
            "--json", "url,tagName,assets",
        ]).stdout
    )
    if release.get("tagName") != tag:
        raise SkillCtlError(f"Release tag mismatch: {release.get('tagName')} != {tag}")
    assets = validate_release_assets(str(tag), release.get("assets", []))
    skill_path = str(entry["path"]).replace("\\", "/")
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in skill_path.split("/"))
    encoded_tag = urllib.parse.quote(str(tag), safe="")
    run(["gh", "api", f"repos/{repo}/contents/{encoded_path}?ref={encoded_tag}"])
    install_url = f"https://github.com/{repo}/tree/{tag}/{skill_path}"
    return {
        "ok": True,
        "operation": "verify-release",
        "skill": args.skill,
        "tag": tag,
        "workflow": workflow,
        "release_url": release["url"],
        "assets": assets,
        "install_url": install_url,
        "checks": {
            "workflow_succeeded": True,
            "release_exists": True,
            "zip_uploaded": True,
            "sha256_uploaded": True,
            "install_link_accessible": True,
        },
    }


def command_release(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        raise SkillCtlError("Repository has not been initialized with Git")
    entry = catalog_entry(root, args.skill)
    verification = validate_skill(root, args.skill)
    if not verification["valid"]:
        raise SkillCtlError(f"Skill validation failed: {verification['errors']}")
    current = entry["version"]
    target_version = bump_version(current, args.bump, args.version)
    tag = f"{args.skill}-v{target_version}"
    branch = load_json(root / REPOSITORY_FILE).get("default_branch", "main")
    skill_path = str(entry.get("path", f"{SKILLS_DIR}/{args.skill}")).replace("\\", "/")
    catalog_path = CATALOG_FILE.as_posix()
    unexpected = [p for p in git_changes(root) if not (p == catalog_path or p == skill_path or p.startswith(skill_path + "/"))]
    if unexpected:
        raise SkillCtlError(f"Unrelated working tree changes block release: {unexpected}")
    if run(["git", "tag", "--list", tag], cwd=root).stdout.strip():
        raise SkillCtlError(f"Tag already exists: {tag}")
    changed = git_changes(root)
    plan = {"operation": "release", "skill": args.skill, "current_version": current, "target_version": target_version, "tag": tag, "branch": branch, "changed_files": changed, "commit_message": args.commit_message or f"release({args.skill}): v{target_version}", "release_title": f"{args.skill} v{target_version}"}
    if not args.yes:
        return {"ok": True, "preview": True, **plan}
    run(["gh", "auth", "status", "-h", "github.com"])
    data = catalog(root)
    for item in data["skills"]:
        if item["name"] == args.skill:
            item["version"] = target_version
            item["release_tag"] = tag
    write_json(root / CATALOG_FILE, data)
    sync_readme_catalog(root, data)
    post_validation = validate_skill(root, args.skill)
    if not post_validation["valid"]:
        raise SkillCtlError(f"Post-version validation failed: {post_validation['errors']}")
    run(["git", "add", "--", skill_path, catalog_path, "README.md"], cwd=root)
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root).stdout.strip()
    if not staged:
        raise SkillCtlError("Release has no staged changes")
    run(["git", "commit", "-m", plan["commit_message"]], cwd=root)
    run(["git", "push", "origin", branch], cwd=root)
    run(["git", "tag", "-a", tag, "-m", plan["release_title"]], cwd=root)
    run(["git", "push", "origin", tag], cwd=root)
    notes_args = ["--notes-file", args.notes_file] if args.notes_file else ["--generate-notes"]
    repo = load_json(root / REPOSITORY_FILE)["github_repository"]
    existing_release = run(["gh", "release", "view", tag, "--repo", repo], cwd=root, check=False)
    if existing_release.returncode != 0:
        created = run(
            ["gh", "release", "create", tag, "--repo", repo, "--title", plan["release_title"], *notes_args],
            cwd=root,
            check=False,
        )
        if created.returncode != 0:
            run(["gh", "release", "view", tag, "--repo", repo], cwd=root)
    final_verification = command_verify_release(
        argparse.Namespace(skill=args.skill, tag=tag, wait_seconds=args.wait_seconds), root
    )
    return {"ok": True, "preview": False, **plan, "published": True, "verification": final_verification}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillctl", description="Manage a versioned multi-skill repository")
    parser.add_argument("--repo-root", help="Skill repository root")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("skill", nargs="?")
    verify.add_argument("--all", action="store_true")

    register = sub.add_parser("register")
    register.add_argument("skill")
    register.add_argument("--category", required=True)
    register.add_argument("--version", default="1.0.0")
    register.add_argument("--description")
    register.add_argument("--yes", action="store_true")

    sync = sub.add_parser("sync")
    sync.add_argument("--yes", action="store_true")

    for name in ("status", "diff", "check"):
        cmd = sub.add_parser(name)
        cmd.add_argument("skill")
        cmd.add_argument("--agent", choices=["codex"], default="codex")
        cmd.add_argument("--dest")

    link = sub.add_parser("link")
    link.add_argument("skill")
    link.add_argument("--agent", choices=["codex"], default="codex")
    link.add_argument("--dest")
    link.add_argument("--replace", action="store_true")
    link.add_argument("--yes", action="store_true")

    for name in ("install", "update"):
        cmd = sub.add_parser(name)
        cmd.add_argument("skill")
        cmd.add_argument("--agent", choices=["codex"], default="codex")
        cmd.add_argument("--dest")
        cmd.add_argument("--source", choices=["local", "github"], default="github")
        cmd.add_argument("--ref")
        cmd.add_argument("--force", action="store_true")
        cmd.add_argument("--yes", action="store_true")

    rollback = sub.add_parser("rollback")
    rollback.add_argument("skill")
    rollback.add_argument("--agent", choices=["codex"], default="codex")
    rollback.add_argument("--dest")
    rollback.add_argument("--yes", action="store_true")

    verify_release = sub.add_parser("verify-release")
    verify_release.add_argument("skill")
    verify_release.add_argument("--tag")
    verify_release.add_argument("--wait-seconds", type=int, default=300)

    release = sub.add_parser("release")
    release.add_argument("skill")
    release_group = release.add_mutually_exclusive_group(required=True)
    release_group.add_argument("--bump", choices=["patch", "minor", "major"])
    release_group.add_argument("--version")
    release.add_argument("--commit-message")
    release.add_argument("--notes-file")
    release.add_argument("--wait-seconds", type=int, default=300)
    release.add_argument("--yes", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        root = find_repo_root(args.repo_root)
        if args.command == "verify":
            payload = command_verify(args, root)
        elif args.command == "register":
            payload = command_register(args, root)
        elif args.command == "sync":
            payload = command_sync(args, root)
        elif args.command == "status":
            payload = command_status(args, root)
        elif args.command == "diff":
            payload = command_diff(args, root)
        elif args.command == "check":
            payload = command_check(args, root)
        elif args.command == "link":
            payload = command_link(args, root)
        elif args.command == "install":
            payload = install_or_update(args, root, updating=False)
        elif args.command == "update":
            payload = install_or_update(args, root, updating=True)
        elif args.command == "rollback":
            payload = command_rollback(args, root)
        elif args.command == "verify-release":
            payload = command_verify_release(args, root)
        elif args.command == "release":
            payload = command_release(args, root)
        else:
            raise SkillCtlError(f"Unsupported command: {args.command}")
        return emit(payload, args.json, 0 if payload.get("ok") else 1)
    except SkillCtlError as exc:
        return emit({"ok": False, "operation": getattr(args, "command", None), "error": str(exc)}, args.json, 1)
    except KeyboardInterrupt:
        return emit({"ok": False, "operation": getattr(args, "command", None), "error": "Interrupted"}, args.json, 130)


if __name__ == "__main__":
    raise SystemExit(main())
