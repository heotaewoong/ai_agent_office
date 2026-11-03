#!/usr/bin/env python3
"""Bounded, read-only Hermes configuration audit. Never imports or executes Hermes."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import stat

import yaml

PROFILES = ("lumi", "ada", "ethan", "sam", "oliver", "noah", "mia", "mybots-sage")
EVENTS = ("pre_tool_call", "post_tool_call", "pre_llm_call", "post_llm_call", "pre_verify",
          "on_session_start", "on_session_end", "on_skill_lifecycle", "subagent_start", "subagent_stop",
          "pre_approval_request", "post_approval_response")
MAX_BYTES = 262144
METADATA_FILES = ("config.yaml", ".env", "webhook_subscriptions.json", "shell-hooks-allowlist.json")


class ConfigLoader(yaml.SafeLoader):
    """Keep YAML 1.2's off/on strings and reject ambiguous duplicate keys."""


ConfigLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
ConfigLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"), list("tTfF"))


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("ambiguous mapping")
        result[key] = loader.construct_object(value_node)
    return result


ConfigLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _read(home, relative, expected_uid, *, contents=False):
    """Open each directory with no-follow, then the fixed file; never traverse links."""
    descriptors = []
    try:
        home = Path(home)
        if not home.is_absolute() or ".." in home.parts:
            return {"status": "unsafe_path"}, None
        parts = home.parts[1:] + tuple(relative.parts)
        current = Path(home.anchor)
        restricted = False
        for index, part in enumerate(parts):
            current /= part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode):
                return {"status": "unsafe_path"}, None
            within_home = index >= len(home.parts) - 2
            if within_home and expected_uid is not None and info.st_uid != expected_uid:
                return {"status": "owner_mismatch"}, None
            final = index == len(parts) - 1
            if final and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                return {"status": "unsafe_path"}, None
            if not final and not stat.S_ISDIR(info.st_mode):
                return {"status": "unsafe_path"}, None
            if not final:
                restricted |= stat.S_IMODE(info.st_mode) & 0o077 == 0
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            if not final:
                flags |= getattr(os, "O_DIRECTORY", 0)
            if os.name == "posix":
                if not descriptors:
                    descriptors.append(os.open(home.anchor, os.O_RDONLY | os.O_DIRECTORY))
                fd = os.open(part, flags, dir_fd=descriptors[-1])
                descriptors.append(fd)
                opened = os.fstat(fd)
                if within_home and expected_uid is not None and opened.st_uid != expected_uid:
                    return {"status": "owner_mismatch"}, None
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    return {"status": "changed_during_read"}, None
            else:
                # Windows is fixture-only; the CLI refuses to audit there.
                if not final:
                    continue
                fd = os.open(current, flags)
                descriptors.append(fd)
                opened = os.fstat(fd)
            if final:
                if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                    return {"status": "unsafe_path"}, None
                result = {"status": "present", "mode": f"{stat.S_IMODE(opened.st_mode):04o}" if os.name == "posix" else "unknown",
                          "uid": opened.st_uid if os.name == "posix" else None,
                          "ancestor_access": "restricted" if restricted else "not_confirmed"}
                if not contents:
                    return result, None
                if opened.st_size > MAX_BYTES:
                    return {"status": "too_large"}, None
                data = os.read(fd, MAX_BYTES + 1)
                after = os.fstat(fd)
                if len(data) > MAX_BYTES or (opened.st_mtime_ns, opened.st_size) != (after.st_mtime_ns, after.st_size):
                    return {"status": "changed_during_read"}, None
                return result, data
    except FileNotFoundError:
        return {"status": "missing"}, None
    except (OSError, ValueError):
        return {"status": "unreadable"}, None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return {"status": "unsafe_path"}, None


def _document(home, relative, expected_uid, *, json_only=False):
    metadata, data = _read(home, relative, expected_uid, contents=True)
    if data is None:
        return metadata, None
    try:
        text = data.decode("utf-8-sig")
        value = json.loads(text) if json_only else yaml.load(text, Loader=ConfigLoader)
        if not isinstance(value, dict):
            raise ValueError("not a mapping")
        return metadata, value
    except (ValueError, yaml.YAMLError, RecursionError):
        return {**metadata, "status": "invalid"}, None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _enum(value, choices):
    return value if isinstance(value, str) and value in choices else "unknown"


def _boolean(value):
    return value if isinstance(value, bool) else "unknown"


def _secret_present(value):
    return isinstance(value, str) and bool(value.strip()) and value != "INSECURE_NO_AUTH"


def _routes(value):
    if not isinstance(value, dict):
        return {"route_count": "unknown", "authenticated_route_count": "unknown"}
    return {"route_count": len(value), "authenticated_route_count": sum(
        _secret_present(_dict(route).get("secret")) for route in value.values())}


def _policy(config):
    if config is None:
        return {"approvals_mode": "unknown", "deny_rule_count": "unknown", "terminal_backend": "unknown",
                "skills_write_approval": "unknown", "shell_hook_event_counts": {event: "unknown" for event in EVENTS},
                "other_hook_section_count": "unknown"}
    approvals, terminal, skills = (_dict(config.get(key)) for key in ("approvals", "terminal", "skills"))
    hooks = config.get("hooks", {})
    hooks = hooks if isinstance(hooks, dict) else None
    counts = {event: len(hooks[event]) if isinstance(hooks.get(event), list) else (0 if event not in hooks else "unknown")
              for event in EVENTS} if hooks is not None else {event: "unknown" for event in EVENTS}
    deny = approvals.get("deny")
    return {"approvals_mode": _enum(approvals.get("mode"), ("manual", "smart", "off")),
            "deny_rule_count": len(deny) if isinstance(deny, list) else "unknown",
            "terminal_backend": _enum(terminal.get("backend"), ("local", "docker", "ssh", "modal", "daytona", "sandbox")),
            "skills_write_approval": _boolean(skills.get("write_approval")),
            "shell_hook_event_counts": counts,
            "other_hook_section_count": sum(key not in EVENTS for key in hooks) if hooks is not None else "unknown"}


def audit(home, *, profiles=("lumi",), expected_uid=None):
    """Return only allowlisted enum values, counts, booleans and file metadata."""
    profiles = tuple(profiles)
    if any(profile not in PROFILES for profile in profiles) or len(set(profiles)) != len(profiles):
        raise ValueError("profiles must be unique allowlisted names")
    if expected_uid is None and os.name == "posix":
        expected_uid = os.getuid()
    rows = []
    for profile in ("default", *profiles):
        prefix = Path() if profile == "default" else Path("profiles") / profile
        files = {name: _read(home, prefix / name, expected_uid)[0] for name in METADATA_FILES}
        config_metadata, config = _document(home, prefix / "config.yaml", expected_uid)
        config_valid = config is not None
        files["config.yaml"] = config_metadata
        policy = _policy(config)
        config = config if config_valid else {}
        webhook = _dict(_dict(config.get("platforms")).get("webhook"))
        extra = _dict(webhook.get("extra"))
        host = extra.get("host")
        try:
            loopback = ipaddress.ip_address(host).is_loopback if isinstance(host, str) else "unknown"
        except ValueError:
            loopback = True if host == "localhost" else "unknown"
        sub_metadata, subscriptions = _document(home, prefix / "webhook_subscriptions.json", expected_uid, json_only=True)
        files["webhook_subscriptions.json"] = sub_metadata
        memory, mem0 = _dict(config.get("memory")), _dict(config.get("mem0"))
        actions = []
        if policy["approvals_mode"] == "off":
            actions.append("approvals_off")
        if policy["skills_write_approval"] is not True:
            actions.append("review_skills_write_gate")
        if webhook.get("enabled") is True and loopback is not True:
            actions.append("review_webhook_bind")
        for name, metadata in files.items():
            if metadata["status"] not in ("present", "missing"):
                actions.append("review_file_" + name)
            elif metadata.get("mode") not in (None, "unknown", "0600", "0400") and metadata["status"] == "present":
                actions.append("review_file_mode_" + name)
        rows.append({"profile": profile, "config_status": config_metadata["status"], "files": files,
                     "token_metadata": "unknown_not_inspected", "policy": policy,
                     "webhook": {"enabled": _boolean(webhook.get("enabled")), "loopback": loopback,
                                 "global_auth_present": _secret_present(extra.get("secret")) if config_valid else "unknown",
                                 "static_routes": _routes(extra.get("routes", {}) if config_valid else None),
                                 "subscriptions": {"status": sub_metadata["status"], **_routes(subscriptions)}},
                     "memory": {"provider": _enum(memory.get("provider", memory.get("backend")), ("mem0", "local", "file", "none")),
                                "mem0_config_key_present": _secret_present(mem0.get("api_key", memory.get("api_key"))) if config_valid else "unknown",
                                "mem0_process_key_present": bool(os.environ.get("MEM0_API_KEY"))},
                     "action_needed": actions})
    return {"schema_version": 1, "read_only": True, "runtime_policy": "unknown", "profiles": rows,
            "limits": ["Configuration snapshot only; environment, hosted-room/session overrides and loaded runtime policy are not resolved.",
                       "No network, model, fix, file mutation, env/token contents, memory bodies, hook scripts or recursive discovery.",
                       "POSIX mode bits do not prove exposure; ancestor directories, ACLs and service isolation need separate review.",
                       "Missing settings remain unknown; native defaults are version-dependent. Hooks counted here are configured shell hooks only."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, action="append", default=None)
    args = parser.parse_args()
    if os.name != "posix":
        parser.exit(2, "Audit CLI requires POSIX no-follow and owner checks.\n")
    try:
        report = audit(args.hermes_home, profiles=tuple(args.profile) if args.profile is not None else ("lumi",))
    except ValueError:
        parser.exit(2, "Invalid audit scope.\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(p["config_status"] == "present" for p in report["profiles"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
