#!/usr/bin/env python3
"""Check local handoff structure and readiness declarations, never live systems."""
import argparse
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
SECRET_REF = re.compile(r"^(env|secret|vault):[A-Za-z0-9_./:-]+$")
FIELD_TYPES = {"text", "number", "money", "datetime", "date", "enum", "relation", "rich_text", "boolean"}
SENSITIVE_KEYS = {"password", "token", "apikey", "accesstoken", "authorization", "databaseurl", "connectionstring", "secretvalue"}
ROOT_KEYS = {"schemaVersion", "companyName", "status", "workspaceRef", "timezone", "blueprint", "runtime", "fields", "rules", "channels", "cases", "unresolved"}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate(data, require_ready=False):
    errors = []
    warnings = []

    def error(path, message):
        # Only schema paths and fixed messages are returned, never input values.
        errors.append(f"{path}: {message}")

    def sensitive(value, path="$"):
        if isinstance(value, dict):
            for index, (key, item) in enumerate(value.items()):
                child = f"{path}.property[{index}]"
                if re.sub(r"[^a-z]", "", key.lower()) in SENSITIVE_KEYS:
                    error(child, "credential-like property forbidden; use a Secret reference")
                sensitive(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                sensitive(item, f"{path}[{index}]")
        elif isinstance(value, str):
            if re.search(r"(?:postgres(?:ql)?|redis)://|https?://[^\s/]+:[^\s/]+@|\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{16,}", value, re.I):
                error(path, "possible credential/connection string; do not store secret values")

    def obj(value, keys, path):
        if not isinstance(value, dict):
            error(path, "must be an object")
            return {}
        if set(value) != set(keys):
            error(path, "property set does not match the handoff format")
        return value

    def text(value, path, required=False):
        if value is not None and not isinstance(value, str):
            error(path, "must be a string or null")
        if required and not nonempty(value):
            error(path, "nonempty string required")

    def strings(value, path):
        if not isinstance(value, list) or any(not nonempty(v) for v in value):
            error(path, "must be a list of nonempty strings")
            return []
        if len(value) != len(set(value)):
            error(path, "duplicate values")
        return value

    def choice(value, options, path):
        if not isinstance(value, str) or value not in options:
            error(path, "unsupported value")

    def flag(value, path):
        if type(value) is not bool:
            error(path, "must be boolean")

    sensitive(data)
    root = obj(data, ROOT_KEYS, "$")
    if root.get("schemaVersion") != "chat-signal.handoff.v1":
        error("schemaVersion", "unsupported schema")
    choice(root.get("status"), {"draft", "ready_for_validation"}, "status")
    ready = root.get("status") == "ready_for_validation" or require_ready
    if require_ready and root.get("status") != "ready_for_validation":
        error("status", "ready_for_validation is required")
    text(root.get("companyName"), "companyName", ready)
    text(root.get("workspaceRef"), "workspaceRef", ready)
    text(root.get("timezone"), "timezone", ready)
    if nonempty(root.get("timezone")):
        try:
            ZoneInfo(root["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            error("timezone", "IANA timezone unknown or timezone database unavailable")

    blueprint = obj(root.get("blueprint"), {"path", "version", "confirmed"}, "blueprint")
    for key in ("path", "version"):
        text(blueprint.get(key), f"blueprint.{key}", ready)
    flag(blueprint.get("confirmed"), "blueprint.confirmed")
    if ready and blueprint.get("confirmed") is not True:
        error("blueprint.confirmed", "confirmed source required before validation")

    runtime = obj(root.get("runtime"), {"artifactRef", "version", "capabilities", "verificationRef"}, "runtime")
    for key in ("artifactRef", "version", "verificationRef"):
        text(runtime.get(key), f"runtime.{key}", ready)
    capabilities = set(strings(runtime.get("capabilities"), "runtime.capabilities"))
    if ready and not capabilities:
        error("runtime.capabilities", "verified capability declarations required")

    def rows(name, keys):
        value = root.get(name)
        if not isinstance(value, list):
            error(name, "must be an array")
            return []
        if ready and not value:
            error(name, "at least one item required for this enabled handoff")
        result = []
        ids = set()
        for index, raw in enumerate(value):
            path = f"{name}[{index}]"
            row = obj(raw, keys, path)
            identity = row.get("id")
            if not isinstance(identity, str) or not IDENTIFIER.fullmatch(identity):
                error(path + ".id", "stable identifier required")
            elif identity in ids:
                error(path + ".id", "duplicate identifier")
            else:
                ids.add(identity)
            result.append((row, path))
        return result

    fields = rows("fields", {"id", "meaning", "source", "writer", "writePolicy", "mapping", "confirmed", "verified"})
    field_ids = {r["id"] for r, _ in fields if isinstance(r.get("id"), str)}
    write_targets = set()
    for row, path in fields:
        text(row.get("meaning"), path + ".meaning", ready)
        choice(row.get("source"), {"chat", "manual", "crm_workflow", "external_verified"}, path + ".source")
        choice(row.get("writer"), {"automation", "human", "crm_workflow"}, path + ".writer")
        choice(row.get("writePolicy"), {"auto", "review", "read_only"}, path + ".writePolicy")
        for key in ("confirmed", "verified"):
            flag(row.get(key), path + "." + key)
            if ready and row.get(key) is not True:
                error(path + "." + key, "must be true before validation")
        if row.get("writer") != "automation" and row.get("writePolicy") != "read_only":
            error(path + ".writePolicy", "automation must not write fields owned by another writer")
        mapping = obj(row.get("mapping"), {"object", "field", "type", "enumValues"}, path + ".mapping")
        for key in ("object", "field", "type"):
            text(mapping.get(key), path + ".mapping." + key, ready)
        if mapping.get("type") is not None:
            choice(mapping.get("type"), FIELD_TYPES, path + ".mapping.type")
        enums = mapping.get("enumValues")
        if not isinstance(enums, dict) or any(not nonempty(k) or not nonempty(v) for k, v in enums.items()):
            error(path + ".mapping.enumValues", "must map nonempty business labels to internal values")
        elif ready and mapping.get("type") == "enum" and not enums:
            error(path + ".mapping.enumValues", "enum mapping required")
        if row.get("writePolicy") in ("auto", "review") and all(nonempty(mapping.get(k)) for k in ("object", "field")):
            target = (mapping["object"], mapping["field"])
            if target in write_targets:
                error(path + ".mapping", "duplicate automation write target; define a single business owner")
            write_targets.add(target)

    cases = rows("cases", {"id", "kind", "input", "expected"})
    case_ids = {r["id"] for r, _ in cases if isinstance(r.get("id"), str)}
    kinds = {}
    for row, path in cases:
        choice(row.get("kind"), {"positive", "boundary"}, path + ".kind")
        for key in ("input", "expected"):
            text(row.get(key), path + "." + key, ready)
        if isinstance(row.get("id"), str):
            kinds[row["id"]] = row.get("kind") if isinstance(row.get("kind"), str) else None

    rules = rows("rules", {"id", "definition", "fieldIds", "requires", "executor", "confirmed", "caseIds"})
    for row, path in rules:
        text(row.get("definition"), path + ".definition", ready)
        choice(row.get("executor"), {"automation", "crm_workflow"}, path + ".executor")
        flag(row.get("confirmed"), path + ".confirmed")
        if ready and row.get("confirmed") is not True:
            error(path + ".confirmed", "confirmed rule required")
        for key, allowed in (("fieldIds", field_ids), ("caseIds", case_ids), ("requires", capabilities)):
            refs = strings(row.get(key), path + "." + key)
            if ready and not refs:
                error(path + "." + key, "at least one reference required")
            # Unknown runtime capability is an intentional draft gap, but dangling field/case references are errors.
            if set(refs) - allowed:
                if key == "requires" and not ready:
                    warnings.append(path + ".requires: runtime capability gap")
                else:
                    error(path + "." + key, "unresolved reference or unsupported runtime capability")
        selected = {kinds.get(x) for x in row.get("caseIds", []) if isinstance(x, str)} if isinstance(row.get("caseIds"), list) else set()
        if ready and not {"positive", "boundary"}.issubset(selected):
            error(path + ".caseIds", "positive and boundary cases required")

    channels = rows("channels", {"id", "provider", "instanceRef", "ownerRef", "secretRef", "configured"})
    instances = set()
    for row, path in channels:
        for key in ("provider", "instanceRef", "ownerRef", "secretRef"):
            text(row.get(key), path + "." + key, ready)
        flag(row.get("configured"), path + ".configured")
        if ready and row.get("configured") is not True:
            error(path + ".configured", "configured declaration required")
        if nonempty(row.get("secretRef")) and not SECRET_REF.fullmatch(row["secretRef"]):
            error(path + ".secretRef", "use env:, secret: or vault: reference, never the secret value")
        if all(nonempty(row.get(k)) for k in ("provider", "instanceRef")):
            identity = (row["provider"], row["instanceRef"])
            if identity in instances:
                error(path + ".instanceRef", "duplicate provider instance binding")
            instances.add(identity)

    unresolved = strings(root.get("unresolved"), "unresolved")
    if ready and unresolved:
        error("unresolved", "move excluded capabilities to deployment notes; resolve enabled-scope gaps")
    if not ready:
        warnings.append("Draft only; incomplete declarations do not permit deployment or writes.")
    warnings.append("Static check only: no live identity, credentials, mappings, capability behavior or deployment was verified.")
    return {"ok": not errors, "readyDeclaration": ready and not errors, "errors": errors, "warnings": warnings}


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        raw = args.file.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError("File too large")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
        result = validate(data, args.require_ready)
    except (OSError, ValueError, RecursionError):
        result = {"ok": False, "readyDeclaration": False, "errors": ["Unable to read valid bounded UTF-8 JSON with unique properties."], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
