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


def dangerous_options(tokens):
    """Inspect only rm/Git argv already bounded and tokenized from original source by native code."""
    if not tokens:
        return False
    executable = tokens[0].rsplit("/", 1)[-1]
    if executable == "rm":
        for token in tokens[1:]:
            if token == "--":
                break
            if token == "--recursive":
                return True
            if (token.startswith("-") and not token.startswith("--")
                    and set(token[1:]) <= set("fiIrRdv") and set(token[1:]) & {"r", "R"}):
                return True
        return False
    if executable != "git":
        return False
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        token = tokens[index]
        if token in {"-C", "-c"}:
            index += 2
        elif token.startswith(("-C", "-c")) or token in {
                "-p", "-P", "--paginate", "--no-pager", "--bare", "--no-replace-objects",
                "--no-lazy-fetch", "--no-optional-locks", "--no-advice"}:
            index += 1
        else:
            return False  # Unknown global grammar is outside this bounded check.
    if index >= len(tokens) or tokens[index] != "push":
        return False
    index += 1
    options = True
    while index < len(tokens):
        token = tokens[index]
        if options and token == "--":
            options = False
        elif token.startswith("+"):
            return True  # Positive refspecs keep their meaning after the option separator.
        elif options and token.startswith("--"):
            option, equals, _ = token.partition("=")
            if option in {"--repo", "--receive-pack", "--exec", "--push-option"}:
                index += not bool(equals)
            elif option in {"--force", "--force-with-lease", "--force-if-includes"}:
                return True
        elif options and token.startswith("-"):
            for offset, letter in enumerate(token[1:], 1):
                if letter == "o":
                    index += offset == len(token) - 1
                    break  # Remaining characters, or the next argv, are the push-option value.
                if letter == "f":
                    return True
                if letter not in "vqndu46":
                    break
        index += 1
    return False


def original_option_block(command, detector):
    pending, seen = [command], set()
    while pending:
        source = pending.pop()
        if source in seen:
            continue
        seen.add(source)
        for start, _, word in detector._iter_shell_command_word_spans(source):
            executable = detector._deobfuscate_shell_word_for_detection(word).rsplit("/", 1)[-1]
            if executable not in {"rm", "git"}:
                continue
            segment = detector._shell_command_segment(source, start)
            # shortcut: original redirections require argv provenance beyond this small option check.
            if any(kind == "char" and quote is None and segment[i] in "<>"
                   for kind, i, _, quote in detector._scan_shell(segment, comments=True)):
                continue
            tokens = detector._shell_segment_tokens(segment, 0)
            if tokens and dangerous_options(tokens):
                return True
        for description, payload in detector._execution_flag_findings(source):
            if description == "shell command via -c/-lc flag" and isinstance(payload, str):
                pending.append(payload)
    return False


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
    if original_option_block(command, detector):
        return block("original_command_options")
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
