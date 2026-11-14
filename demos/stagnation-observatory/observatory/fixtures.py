"""Purpose: author transparent development coverage, not a held-out benchmark.

Contract: trusted fixture authors return traces, evaluator labels and a harness
mapping. Replay receives agent events/store separately from spec/digest pins.
Replay never receives labels or family names. Six families share four variants.
Invariant: labels encode the progress policy's thresholds by construction;
they are not an independent measure of useful work or a generalization test.
Rationale: a small matrix makes failure classes inspectable before a real study.
Failure: disagreements are preserved as measured false positives/negatives.
Evidence: tests/test_core.py verifies fixture balance and metric accounting.
"""
from .core import canonical, sha256

FAMILIES = ("exact_loop", "paraphrase_loop", "verified_work", "legitimate_wait", "cosmetic_work", "expired_wait")
PARAPHRASES = (
    "I am reviewing the packet requirements.",
    "The next step remains collecting the same attachments.",
    "Document readiness deserves another careful pass.",
    "We should revisit what the reviewer still needs.",
    "My focus is on preparing materials for the handoff.",
    "Further attention to the packet is the current priority.",
)


def event(task: str, tick: int, text: str, *, kind="message", criterion=None, artifact=None,
          until=None, wake=None) -> dict:
    return {"event_id": f"event{tick}", "task_id": task, "tick": tick, "kind": kind,
            "role": "controller" if kind == "wait" else "agent", "text": text,
            "criterion_id": criterion, "artifact_id": artifact, "wait_until": until,
            "wake_condition": wake}


def artifact(task: str, criterion: str, items: list[str]) -> tuple[str, str]:
    """Author a fixture's bytes and pin before exposing a mutable agent store.

    This helper belongs to the trusted fixture generator, never the verifier.
    The replay must not recompute a trusted pin from agent-supplied bytes. Exact
    item IDs demonstrate the call path; matching them does not prove work quality.
    """
    content = canonical({"task_id": task, "criterion_id": criterion, "items": items}).decode("utf-8")
    return content, sha256(content.encode("utf-8"))


def fixture_bank() -> tuple[list[dict], dict, dict]:
    traces, labels, harness = [], {}, {}
    for family in FAMILIES:
        for variant in range(4):
            index = len(traces) + 1
            trace_id, task = f"trace{index:02d}", f"packet{index:02d}"
            criteria = {f"stage{i}": [f"section{n}" for n in range(1, i + 1)] for i in range(1, 7)}
            trace = {"trace_id": trace_id, "task_id": task, "events": []}
            inputs = {"spec": {"task_id": task, "criteria": criteria, "waits": {}},
                      "pinned_digests": {}, "store": {}}
            repeated = ("I am checking the packet.", "Reviewing the attachment inventory.",
                        "The packet is under review.", "Working on the document bundle.")[variant]
            if family in ("legitimate_wait", "expired_wait"):
                until = 7 if family == "legitimate_wait" else 4
                # Author policy first. The trace is produced from this trusted
                # declaration; no trace field is copied back into authorization.
                # Evidence: test_fixture_wait_policy_does_not_copy_agent_events.
                declaration = {"tick": 1, "wait_until": until,
                               "wake_condition": "Attachment service responds; otherwise expiry permits a new progress check."}
                inputs['spec']['waits']['event1'] = declaration
                trace["events"].append(event(task, 1, "Wait for the external attachment service.", kind="wait",
                                             until=declaration['wait_until'], wake=declaration['wake_condition']))
                end = 6 if family == "legitimate_wait" else 8
                trace["events"].extend(event(task, tick, repeated) for tick in range(2, end + 1))
            else:
                for tick in range(1, 7):
                    if family == "paraphrase_loop":
                        text = PARAPHRASES[(tick - 1 + variant) % len(PARAPHRASES)]
                    else:
                        text = repeated
                    if family in ("verified_work", "cosmetic_work"):
                        artifact_id = f"output{tick}"
                        items = criteria[f"stage{tick}"] if family == "verified_work" else [f"cosmetic{tick}"]
                        content, digest = artifact(task, f"stage{tick}", items)
                        inputs['store'][artifact_id] = content
                        inputs['pinned_digests'][artifact_id] = digest
                        trace["events"].append(event(task, tick, text, kind="result", criterion=f"stage{tick}", artifact=artifact_id))
                    else:
                        trace["events"].append(event(task, tick, text))
            expected = [record["event_id"] for record in trace["events"]
                        if ((family in ("exact_loop", "paraphrase_loop", "cosmetic_work") and record["tick"] >= 3)
                            or (family == "expired_wait" and record["tick"] >= 6))]
            labels[trace_id] = {"family": family, "variant": variant, "positive_event_ids": expected,
                                "title": family.replace("_", " ").capitalize() + f" · {variant + 1}"}
            traces.append(trace)
            harness[trace_id] = inputs
    return traces, labels, harness
