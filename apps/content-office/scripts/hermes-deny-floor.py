#!/usr/bin/env python3
"""Inactive candidate: terminal-only pre_tool_call guard. Never executes tool input."""
import argparse
import fnmatch
import hashlib
import importlib
import json
from pathlib import Path
import sys

MAX_BYTES = 65536


def block(rule):
    # Never echo commands, arguments, credentials, or exception text to the model.
    return {"action": "block", "message": "Deny-floor policy: " + rule}


def load_policy(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("policy size")
    policy = json.loads(raw)
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise ValueError("policy schema")
    for key in ("profiles", "deny", "native_deny_classes"):
        values = policy.get(key)
        if (not isinstance(values, list) or not values or len(values) > 64
                or any(not isinstance(x, str) or not x.strip() or len(x) > 256 for x in values)):
            raise ValueError("policy entries")
    digest = policy.get("native_detection_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("native digest")
    return policy


def merge_deny(existing, additions):
    """Return an additive proposal only; never mutate or persist a profile config."""
    if not isinstance(existing, list) or any(not isinstance(x, str) for x in existing):
        raise ValueError("existing deny must be a list")
    return list(dict.fromkeys(existing + additions))


def evaluate(payload, policy, detector):
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "pre_tool_call":
        return block("invalid_event")
    profile = payload.get("profile")
    if not isinstance(profile, str) or not profile:
        return block("missing_profile")
    if profile not in policy["profiles"] or payload.get("tool_name") != "terminal":
        return {}
    args = payload.get("tool_input")
    command = args.get("command") if isinstance(args, dict) else None
    if not isinstance(command, str) or not command.strip() or len(command) > 32768:
        return block("invalid_command")
    if detector.detect_hardline_command(command)[0]:
        return block("native_hardline")
    # shortcut: native text classification is bounded, not a shell sandbox. Re-test on native upgrades.
    for variant in detector._deny_command_variants(command):
        for pattern in policy["deny"]:
            if fnmatch.fnmatchcase(variant.lower().strip(), pattern.lower()):
                return block("declarative_deny")
    # The public classifier returns its first match. Check every selected native rule so harmless
    # quoted text matching an earlier class cannot hide a credential upload in the same command.
    for variant in detector._command_detection_variants(command):
        lowered = detector._lower_preserving_flags(variant)
        masked = None
        for pattern, description in detector.DANGEROUS_PATTERNS_COMPILED:
            if description not in policy["native_deny_classes"]:
                continue
            candidate = lowered
            if description in detector._QUOTE_MASKED_DANGEROUS_DESCRIPTIONS:
                if masked is None:
                    masked = detector._lower_preserving_flags(detector._mask_quoted_prose(variant))
                candidate = masked
            if pattern.search(candidate):
                return block("native_danger_class")
    return {}


def load_native(root, policy):
    root = Path(root)
    if not root.is_absolute():
        raise ValueError("native root must be absolute")
    source = root / "tools" / "approval_detection.py"
    if hashlib.sha256(source.read_bytes()).hexdigest() != policy["native_detection_sha256"]:
        raise ValueError("native detector changed")
    sys.path.insert(0, str(root))
    detector = importlib.import_module("tools.approval_detection")
    if Path(detector.__file__).resolve() != source.resolve():
        raise ValueError("unexpected native module")
    known = {description for _, description in detector.DANGEROUS_PATTERNS_COMPILED}
    if not set(policy["native_deny_classes"]).issubset(known):
        raise ValueError("unknown native class")
    return detector


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("input size")
        payload = json.loads(raw)
        parser = argparse.ArgumentParser()
        parser.add_argument("--native-root")
        parser.add_argument("--policy", default=str(Path(__file__).with_name("hermes-deny-floor-policy.json")))
        args = parser.parse_args()
        if not args.native_root:
            raise ValueError("missing native root")
        policy = load_policy(args.policy)
        decision = evaluate(payload, policy, load_native(args.native_root, policy))
    except Exception:
        decision = block("guard_unavailable")
    print(json.dumps(decision, ensure_ascii=True))
    return 2 if decision.get("action") == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
