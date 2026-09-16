#!/usr/bin/env python3
"""Deterministic manager for a versioned multi-skill repository."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(r"E:\AI Workspace\skills")
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
        root = next((p for p in candidates if (p / "catalog.json").is_file()), DEFAULT_REPO_ROOT)
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
    data = load_json(root / "catalog.json")
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


def validate_skill(root: Path, name: str) -> dict[str, Any]:
    entry = catalog_entry(root, name)
    skill_dir = (root / entry.get("path", name)).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if skill_dir.parent != root.resolve():
        errors.append("Skill path must be a direct child of repository root")
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
    return {"ok": all(item["valid"] for item in results), "operation": "verify", "results": results}


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
    result = run(["gh", "api", f"repos/{repo}/contents/catalog.json", "--jq", ".content"])
    try:
        return json.loads(base64.b64decode(result.stdout.strip()).decode("utf-8"))
    except Exception as exc:
        raise SkillCtlError(f"Unable to decode remote catalog: {exc}") from exc


def remote_entry(root: Path, name: str) -> dict[str, Any]:
    repo = load_json(root / "repository.json")["github_repository"]
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
    repo_info = load_json(root / "repository.json")
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
        lock.setdefault("skills", {})[args.skill] = {"repository": load_json(root / "repository.json")["github_repository"], "path": entry.get("path", args.skill), "installed_version": entry.get("version"), "installed_ref": args.ref or entry.get("release_tag") or "local", "content_sha256": installed_digest, "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "source": args.source}
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
    branch = load_json(root / "repository.json").get("default_branch", "main")
    unexpected = [p for p in git_changes(root) if not (p == "catalog.json" or p == args.skill or p.startswith(args.skill + "/"))]
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
    write_json(root / "catalog.json", data)
    post_validation = validate_skill(root, args.skill)
    if not post_validation["valid"]:
        raise SkillCtlError(f"Post-version validation failed: {post_validation['errors']}")
    run(["git", "add", "--", args.skill, "catalog.json"], cwd=root)
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root).stdout.strip()
    if not staged:
        raise SkillCtlError("Release has no staged changes")
    run(["git", "commit", "-m", plan["commit_message"]], cwd=root)
    run(["git", "push", "origin", branch], cwd=root)
    run(["git", "tag", "-a", tag, "-m", plan["release_title"]], cwd=root)
    run(["git", "push", "origin", tag], cwd=root)
    notes_args = ["--notes-file", args.notes_file] if args.notes_file else ["--generate-notes"]
    run(["gh", "release", "create", tag, "--repo", load_json(root / "repository.json")["github_repository"], "--title", plan["release_title"], *notes_args], cwd=root)
    run(["gh", "release", "view", tag, "--repo", load_json(root / "repository.json")["github_repository"], "--json", "url,tagName"], cwd=root)
    return {"ok": True, "preview": False, **plan, "published": True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillctl", description="Manage a versioned multi-skill repository")
    parser.add_argument("--repo-root", help="Skill repository root")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("skill", nargs="?")
    verify.add_argument("--all", action="store_true")

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

    release = sub.add_parser("release")
    release.add_argument("skill")
    release_group = release.add_mutually_exclusive_group(required=True)
    release_group.add_argument("--bump", choices=["patch", "minor", "major"])
    release_group.add_argument("--version")
    release.add_argument("--commit-message")
    release.add_argument("--notes-file")
    release.add_argument("--yes", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        root = find_repo_root(args.repo_root)
        if args.command == "verify":
            payload = command_verify(args, root)
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
