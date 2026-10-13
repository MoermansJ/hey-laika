# Agent PR review rubric

Used by the factory's **review phase** (see `claude/agent-factory.md`). A reviewer
subagent that has NOT seen the implementation session reads this file, the
ticket, the design doc and the PR diff, and judges the PR. Edit this file to
tune what "good enough to merge" means; the next factory run picks it up.

## Inputs the reviewer reads (and nothing else)

1. The ticket: issue body + acceptance criteria (`gh api repos/MoermansJ/hey-laika/issues/<N>`)
2. The design doc: `orchestrator/docs/design/AGENT_TOOL_COMPOSITION_DESIGN.md`
   (the section(s) the ticket references)
3. The PR diff: `gh api repos/MoermansJ/hey-laika/pulls/<PR>/files`
4. Neighbouring code in the same package/module, to judge codebase patterns
5. Earlier review comments on the ticket (`<!-- agent-review-feedback` marker),
   to check that previously requested changes were actually made

The reviewer must not be given the implementer's reasoning or summary.

## Criteria (each is PASS or FAIL)

| # | Criterion | PASS when | FAIL when |
|---|-----------|-----------|-----------|
| 1 | **Satisfies ticket** | Every acceptance criterion in the ticket is implemented and visible in the diff | A criterion is missing, only stubbed, or contradicted |
| 2 | **Follows design doc** | Class/endpoint names, data shapes, and behavior match the referenced design sections | Names/shapes/behavior diverge without a stated reason in the PR body |
| 3 | **Matches codebase patterns** | Package layout, naming, error handling, DI style and logging follow neighbouring code; no new frameworks; Java stays idiomatic Spring; Python only where the adapter already is | Style clashes with surrounding code, duplicates an existing utility, or adds unrelated changes |
| 4 | **Includes tests** | New behavior has unit/slice tests that assert real outcomes (not only "does not throw"), and CI is green | No tests for new logic, or tests that cannot fail |

Overall verdict = **PASS only if all four criteria PASS**. Anything else is FAIL.

Do not fail a PR for taste, for things the ticket did not ask for, or for
anything CI already proves. Be specific: every FAIL must name the file/line and
say what to change, so the implementer can fix it without asking.

## Output format (exact)

The reviewer returns this, and the factory posts it verbatim as a PR comment
and (on FAIL) as a ticket comment:

```
<!-- agent-review -->
<!-- agent-review: verdict=PASS|FAIL ticket=#<N> pr=#<PR> attempt=<K> -->
## Agent review: PASS|FAIL  (attempt K of 3)

| Criterion | Verdict | Notes |
|---|---|---|
| Satisfies ticket | PASS/FAIL | ... |
| Follows design doc | PASS/FAIL | ... |
| Matches codebase patterns | PASS/FAIL | ... |
| Includes tests | PASS/FAIL | ... |

### Required changes (FAIL only)
1. `path/to/File.java`: what to change and why
```

For the ticket comment on FAIL, the same body is used but the first line is
`<!-- agent-review-feedback pr=#<PR> attempt=<K> -->` instead of
`<!-- agent-review -->`.
