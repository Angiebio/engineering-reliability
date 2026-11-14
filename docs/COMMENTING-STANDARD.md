# Comments for human and AI maintainers

Version 4, 14 November 2026, after Flame Johnson's independent third look.

The convention is inspired by Angela N. Johnson's [Frontiers study of expressive code comments](https://doi.org/10.3389/frai.2026.1784973). The paper supports taking comment language seriously as model input; it does not establish that more words universally improve maintenance. This convention is a testable engineering choice.

## The rule

At each nontrivial module, policy boundary, transformation, and experiment boundary, explain **purpose, contract, invariant, rationale, failure, and evidence**. Cover shared facts once at module level. Add local comments where a decision or exception would otherwise be lost between maintainers.

| Field | Required substance |
|---|---|
| Purpose | The human or research need served by this code. |
| Contract | Input/output meaning, source trust, state ownership, and side effects. |
| Invariant | What must remain true after an edit. |
| Rationale | Why this design was chosen, including the relevant tradeoff. |
| Failure | Invalid input, unavailable evidence, interruption, and error behavior. |
| Evidence | The test or protocol section that exercises the actual call path. |

Use natural prose or labeled blocks. A useful metaphor can carry intent, but must sit beside an exact contract. Label hypotheses and interpretations. Avoid narrating ordinary syntax. Keep empirical results in generated reports rather than unversioned comments.

```python
# Purpose: Prevent an invalid evaluation from advancing a model change.
# Contract: Accept ordinary finite numbers; reject bool despite Python's int ancestry.
# Invariant: Malformed measurements cannot satisfy the promotion policy.
# Rationale: NaN makes ordered comparisons false and can bypass a threshold cascade.
# Failure: Raise a validation error before any registry mutation.
# Evidence: Cite the actual nonfinite-input and unchanged-state tests in this package.
```

The example is a template, not a test reference. Implementations must name their real evidence. A comment saying “this never leaks” is not a control; a bounded data contract and an adversarial test can support a narrower statement.

## Review protocol

1. Trace input to public entrypoint to result; verify the comments describe that path.
2. Check every referenced test and source exists and supports its associated claim.
3. Break the invariant deliberately. The relevant test must fail.
4. Update comments and tests together when behavior changes.
5. Remove stale explanatory text when its behavior is removed.
6. Distinguish consistency hashes from authentication, synthetic outcomes from empirical model performance, and simulated authority from production identity controls.
7. Assert the intended reason code and, where several guards share one code, the specific diagnostic. Construct the input so earlier guards pass. A generic exception is not evidence that the named guard ran.
8. Challenge both sides of a property: empty/partial/exact/extra sets; the boundary and one representable step on either side; every action or verdict rather than only the example that motivated the fix.
9. Test each new figure when it is added. Parse its rendered SVG or HTML and compare identities, groups, labels, scale origins, coordinates and outcomes with the computed data. A swapped pair, missing group or invented caption must fail.

No word-count or comment-density quota substitutes for useful context. Evaluate the convention later against concise accurate comments on held-out maintenance tasks, with hidden behavioral tests, invariant preservation, patch size, and cost scored separately.

## Executable comment contracts

The first review found six inaccurate claims despite every named test reference resolving. Reference existence is only a lint check. A maintained safety or correctness claim must also identify what small implementation change would violate it and which named test notices.

Each package records selected contracts in `tests/comment_mutations.json`. A contract names a unique source anchor, a compilable replacement, an adjacent `Mutation:` marker, its claim/finding, and the full unittest names cited in the nearby comment. Policy constants explain their provenance (development choices or technical bounds), why changing them matters, and the test that pins the relevant boundary. Branch comments explain the protected invariant close to the actual decision.

The [shared verifier](../tools/verify_comment_mutations.py) runs only in disposable copies. It requires the cited tests to pass on the original code, applies exactly one listed mutation, and requires those same tests to fail. Syntax errors, missing imports, missing tests, missing comment citations and stale anchors cannot count as successful guard detection. A surviving mutation remains a failure of the claimed contract; the verifier does not silently skip it. Five self-tests challenge the verifier's own attribution rules.

```sh
python -B tools/verify_comment_mutations.py
python -B -m unittest discover -s tools -p test_comment_mutation_runner.py -v
```

The script also works with a separately checked-out package:

```sh
python -B tools/verify_comment_mutations.py --package-dir /path/to/package --output /path/to/evidence.json
```

This is a curated mutation catalog, not a proof that every comment is true or every regression is detectable. Named-test sensitivity, code review, and independent probes answer different questions. Keep semantic limits—such as sparse checkpoints, fixture-sensitive memory packing, local role labels and trial-wide geographic totals—visible alongside caught guards. The empirical comment-ablation workbench remains a separate future study with held-out agent maintenance tasks.

## Keep outside challenges visible

The curated panel is a release condition: its selected contracts must all be caught. That selection cannot estimate general detection performance. A second panel retains the outside reviewer's frozen selections, their earlier outcomes and the current reruns. Keep equivalent and disclosed survivors visible with hollow marks; retain genuine gaps and inconclusive harness failures too. Do not remove a case to improve the score, count an anchor/import failure as detection, or describe a known reviewer catalog as still held out after using it to repair tests.

Outside provenance means someone else selected the edits. TV executes the release rerun and classifies survivors with explicit evidence. The comparison is a maintenance record, not a random sample or evidence of broad model safety. Preserve the reviewer's original scripts and the full commands/results beside the rendered panel.

Traceback exports replace local package/runtime/user-home roots with portable labels before JSON encoding. Test names, source line numbers, assertion values and exception messages remain intact. The release scan must inspect decoded JSON and fail on unreadable files or directories.

## Score a fresh reviewer round before repair

1. Freeze the implementation, tests and generated evidence, and record their hashes before sharing that revision with the reviewer.
2. Have the reviewer select new challenges without disclosing them to the implementer until the first execution is scored. Record who selected and ran them, which revision was tested and every outcome, including survivors and invalid executions.
3. Preserve that first score, the complete selected catalog and the original available output. Do not replace it with a later post-repair score, omit a near-equivalent case to improve the denominator, or invent full execution logs when the reviewer supplied only summaries.
4. Describe the result as held out from the implementer **during that review round**. Once disclosed, those cases are known development checks. A targeted reviewer sample is not a random estimate of defect coverage or clinical safety.
5. If a case later motivates a repair, record the later development outcome separately. A new held-out score requires another previously undisclosed reviewer round and another frozen implementation.

Round 3 is the first such archived strip here: Flame Johnson's original 13/14 on the reviewed `TV-RECHECK-FIXES-13NOV2026` snapshot. T-RM2 remains a visible near-equivalent survivor. For publication, one header string in each demo's report generator changed from the first author's name to the lab's; tests, guards and every other source line are as scored. See [CHANGELOG.md](../CHANGELOG.md).
