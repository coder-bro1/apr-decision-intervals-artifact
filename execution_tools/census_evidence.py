"""Conservative, per-trigger interpretation of controlled census evidence."""
import re


def test_headers(text):
    return sorted(set(re.findall(r"(?m)^--- (\S+)\s*$", text)))


def excluded(trigger, exclusions):
    return any(trigger == x or ("::" not in x and trigger.split("::", 1)[0] == x) for x in exclusions)


def started_tests(text):
    ids, unparsed = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([^\[(]+)(?:\[.*\])?\(([^()]+)\)", line.strip())
        if match:
            ids.append(match[2] + "::" + match[1])
        else:
            unparsed.append(line)
    return ids, unparsed


def test_evidence(log, all_tests, failures, trigger):
    ids, unparsed = started_tests(all_tests)
    pieces = re.split(r"(?m)^--- (.+)\r?$", failures)
    signatures = []
    malformed = bool(pieces[0].strip())
    for i in range(1, len(pieces), 2):
        lines = [x.strip() for x in pieces[i + 1].splitlines() if x.strip()]
        malformed |= not bool(lines)
        signatures.append([pieces[i].strip(), lines[0] if lines else ""])
    reported = re.findall(r"(?m)^Failing tests: (\d+)\s*$", log)
    listed = sorted(re.findall(r"(?m)^\s+- (\S+)\s*$", log))
    # Parameterized executions can start the same method multiple times. The
    # official CLI counts unique failing method identities, not invocations.
    failed_ids = sorted({s[0] for s in signatures})
    valid = (not malformed and not unparsed and trigger in ids
             and set(ids) == {trigger} and reported == [str(len(failed_ids))]
             and listed == failed_ids and all(s[0] == trigger for s in signatures))
    return {"started_count": len(ids), "started_ids": ids, "unparsed_started_entries": unparsed,
            "failure_signatures": sorted(signatures), "evidence_valid": valid,
            "note": "Native formatter startTest events; command completion and failure report are also required."}


def clean(command):
    return command.get("exit_code") == 0 and not command.get("timeout")


def interpreted_test(variant, trigger):
    found = [c for c in variant.get("tests", []) if c.get("trigger") == trigger]
    if len(found) != 1:
        return None
    command = found[0]
    if not clean(command) or not command.get("evidence_valid") or command.get("excluded"):
        return None
    signatures = command["failure_signatures"]
    # These diagnostics are ambiguous environment/harness failures, even when
    # the test method started. Preserve them but do not use as rejection proof.
    ambiguous = ("OutOfMemoryError", "NoClassDefFoundError", "ClassNotFoundException",
                 "ExceptionInInitializerError", "UnsupportedClassVersionError",
                 "NoSuchMethodError", "NoSuchFieldError", "UnsatisfiedLinkError")
    if any(any(token in s[1] for token in ambiguous) for s in signatures):
        return None
    return signatures


def pair(variants, name):
    selected = [v for v in variants if v.get("variant") == name]
    if len(selected) != 2 or {v.get("repeat") for v in selected} != {1, 2}:
        return None
    return sorted(selected, key=lambda v: v["repeat"])


def compile_status(selected):
    if selected is None:
        return "unresolved_missing_repetition"
    if any(v.get("placement_error") for v in selected):
        return "unresolved_placement"
    commands = [v.get("compile", {}) for v in selected]
    if any(not c or c.get("timeout") for c in commands):
        return "unresolved_compile_timeout_or_missing"
    passed = [clean(c) for c in commands]
    if all(passed):
        return "compile_pass"
    if any(passed):
        return "unresolved_compile_disagreement"
    return "compile_command_failed_twice"


def interpret(result, cases):
    variants = result.get("variants", [])
    controls = {k: pair(variants, k) for k in ("fixed", "buggy")}
    controls_compile = all(compile_status(v) == "compile_pass" for v in controls.values())
    complete = result.get("status") == "finished"
    admissible = []
    if controls_compile and complete:
        for trigger in result.get("triggers", []):
            if excluded(trigger, result.get("exclusions", [])):
                continue
            fixed = [interpreted_test(v, trigger) for v in controls["fixed"]]
            buggy = [interpreted_test(v, trigger) for v in controls["buggy"]]
            if fixed == [[], []] and buggy[0] and buggy[0] == buggy[1]:
                admissible.append(trigger)
    findings = []
    for case in cases:
        key = case["candidate_id"]
        selected = pair(variants, key)
        compiled = compile_status(selected)
        status, witnesses = "unresolved_setup_or_controls", []
        if complete and controls_compile:
            if not selected or any(not v.get("placement") for v in selected):
                status = "unresolved_placement_or_repetition"
            elif selected[0]["placement"] != selected[1]["placement"]:
                status = "unresolved_placement_disagreement"
            elif compiled != "compile_pass":
                status = compiled
            elif case.get("compile_only"):
                status = "compile_pass_tests_not_run"
            elif not admissible:
                status = "unresolved_no_admissible_trigger"
            else:
                patterns = [[interpreted_test(v, t) for v in selected] for t in admissible]
                witnesses = [t for t, p in zip(admissible, patterns) if p[0] and p[0] == p[1]]
                inconsistent = any(p[0] is not None and p[1] is not None and p[0] != p[1] for p in patterns)
                if inconsistent:
                    status, witnesses = "unresolved_test_disagreement", []
                elif witnesses:
                    status = "controlled_trigger_failure"
                elif all(p == [[], []] for p in patterns):
                    status = "admissible_triggers_pass_semantics_unknown"
                else:
                    status = "unresolved_missing_test_evidence"
        findings.append({"candidate_id": key, "compile_status": compiled,
                         "evidence_status": status, "rejection_witnesses": witnesses})
    return {"controls_compile": controls_compile, "admissible_triggers": admissible,
            "findings": findings, "labels_changed": False,
            "scope": "Trigger rejection evidence only. Compile-command failures require diagnosis; passes never establish correctness."}
