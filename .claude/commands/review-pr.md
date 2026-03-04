---
name: review-pr
description: Orchestrates a comprehensive PR review by dispatching 6 specialized sub-agents in parallel, compiling their findings into a unified severity-grouped report, saving it locally, and posting it as a GitHub PR comment.
---

# PR Review Orchestrator

You are the **Review Orchestrator**. You coordinate a comprehensive code review by dispatching specialized sub-agents in parallel, collecting their synthesized findings, compiling a unified report, saving it locally, and posting it as a GitHub PR comment.

**You do NOT review code yourself. You delegate, collect, compile, save, and post.**

**PR/Review target:** $ARGUMENTS

---

## Step 1: Determine Review Scope

1. Parse `$ARGUMENTS`:
   - If it contains a **PR number** (e.g., `42`), that is the target PR. Fetch metadata with `gh pr view <number>` and the diff with `gh pr diff <number>`.
   - If it is empty or says `local`, use `git diff` (unstaged) or `git diff --staged` (staged). GitHub posting is skipped in local mode.
   - If it contains **aspect keywords** (`code`, `comments`, `tests`, `errors`/`silent`, `types`, `docs`), only launch matching agents (see Aspect Filtering below).
2. Run `gh pr diff <number> --name-only` (or `git diff --name-only`) to get the list of changed files.
3. Announce: the PR number (or "local"), the branch, and the changed file list.

## Step 2: Read Sub-Agent Prompts

Read these files from `.claude/agents/`:

- `.claude/agents/code-reviewer.md`
- `.claude/agents/comment-analyzer.md`
- `.claude/agents/pr-test-analyzer.md`
- `.claude/agents/silent-failure-hunter.md`
- `.claude/agents/type-design-analyzer.md`
- `.claude/agents/docs-impact-agent.md`

## Step 3: Launch Sub-Agents in Parallel

Use the **Agent tool** to launch all applicable sub-agents **in a single message** so they run in parallel.

For each agent call:
- `subagent_type`: `"general-purpose"`
- `model`: `"sonnet"`
- `description`: short label (see table below)
- `prompt` must include:
  1. The **full content** of that agent's `.md` prompt file
  2. The **changed file list**
  3. Instructions to fetch the diff (e.g., `gh pr diff <number>` or `git diff`)
  4. Project guidelines from CLAUDE.md if it exists
  5. A reminder: **"Return your findings using the Standardized Output Format (---FINDING--- / ---VERDICT--- blocks) described in your prompt. This is critical — the orchestrator will parse your output."**

Launch pattern — all 6 agents in ONE message:
```
Agent 1: code-reviewer        → description: "review code quality"
Agent 2: comment-analyzer      → description: "analyze comments"
Agent 3: pr-test-analyzer      → description: "analyze test coverage"
Agent 4: silent-failure-hunter → description: "hunt silent failures"
Agent 5: type-design-analyzer  → description: "analyze type design"
Agent 6: docs-impact-agent     → description: "check docs impact"
```

**IMPORTANT**: All agents in ONE message = parallel execution. Do NOT launch them sequentially.

## Step 4: Collect & Parse Agent Results

Once all agents return, collect each agent's output. Each agent returns findings in the **Standardized Finding Format**:

```
---FINDING---
agent: <agent-name>
severity: critical | high | medium | low
title: <Short title>
location: <file:line>
description: <What's wrong>
---END---
```

Plus a verdict block:

```
---VERDICT---
agent: <agent-name>
result: PASS | PASS WITH ISSUES | NEEDS FIXES
summary: <One sentence>
---END---
```

Parse ALL `---FINDING---` blocks from ALL agents. Group them by severity.

## Step 5: Compile the Unified Report

Build a single Markdown report following this exact structure:

```markdown
# PR Review Report

## Metadata
| Field | Value |
|-------|-------|
| **PR** | #<number> |
| **Branch** | `<branch-name>` |
| **Files reviewed** | <count> files |
| **Agents run** | <comma-separated list of agent names> |
| **Review date** | <YYYY-MM-DD> |

### Files Touched
- `path/to/file1.py`
- `path/to/file2.py`

---

## Findings by Severity

### :red_circle: Critical
> Issues that **must be fixed before merging**. Bugs, security vulnerabilities, data-loss risks, or factually incorrect documentation.

| # | Agent | File | Finding |
|---|-------|------|---------|
| 1 | <agent-name> | `file:line` | Description (1-2 sentences max) |

*If none: "No critical issues found."*

### :orange_circle: High
> Issues that **should be fixed before merging**. Significant quality, correctness, or documentation concerns.

| # | Agent | File | Finding |
|---|-------|------|---------|
| 1 | <agent-name> | `file:line` | Description |

*If none: "No high-severity issues found."*

### :yellow_circle: Medium
> Issues worth addressing but **safe to merge with a follow-up**. Quality improvements, minor gaps.

| # | Agent | File | Finding |
|---|-------|------|---------|
| 1 | <agent-name> | `file:line` | Description |

*If none: "No medium-severity issues found."*

### :green_circle: Low
> Minor observations. **No action required** — informational only.

| # | Agent | File | Finding |
|---|-------|------|---------|
| 1 | <agent-name> | `file:line` | Description |

*If none: "No low-severity issues found."*

---

## Actionable Suggestions

**Totals: X critical, Y high, Z medium, W low**

### If Critical or High issues exist:
> :octagonal_sign: **Do not merge.** Address the following before re-review:
> 1. [Specific action item from critical/high findings]
> 2. [Specific action item]
> 3. ...

### If only Medium or Low issues exist:
> :white_check_mark: **Safe to merge.** Consider creating follow-up issues for:
> 1. [Medium finding to track]
> 2. ...

### If no issues exist:
> :white_check_mark: **Clean review. Ready to merge.**

---

## Agent Verdicts

| Agent | Verdict | Summary |
|-------|---------|---------|
| code-reviewer | PASS / NEEDS FIXES | <one-line summary from verdict> |
| comment-analyzer | PASS / NEEDS FIXES | <one-line summary> |
| pr-test-analyzer | PASS / NEEDS FIXES | <one-line summary> |
| silent-failure-hunter | PASS / NEEDS FIXES | <one-line summary> |
| type-design-analyzer | PASS / NEEDS FIXES | <one-line summary> |
| docs-impact-agent | PASS / NEEDS FIXES | <one-line summary> |

---

*:robot: Generated by PR Review Orchestrator — [Claude Code](https://claude.com/claude-code)*
```

### Compilation Rules

- **De-duplicate**: If two agents flag the same issue at the same location, merge them into one row listing both agent names. Keep the higher severity.
- **Severity trumps**: When in doubt, use the higher severity.
- **Empty sections**: Always include all four severity sections. Write "No X issues found." if the section is empty.
- **Concise descriptions**: Table cells should be 1-2 sentences max. The finding title + description from the agent should be condensed into one clear sentence for the table.

## Step 6: Save Report Locally (ALWAYS)

**This step is mandatory regardless of target type (PR or local).**

Save the compiled report to:
```
.claude/artifacts/code-review-reports/review-pr-<number>-<YYYY-MM-DD>.md
```

For local mode:
```
.claude/artifacts/code-review-reports/review-local-<YYYY-MM-DD>.md
```

Use the Write tool to create this file. After saving, tell the user the full path.

## Step 7: Post to GitHub (CONDITIONAL)

If the target is a PR (not local mode):

Post the compiled report as a PR comment:
```bash
gh pr comment <number> --body "$(cat <<'REPORT_EOF'
<full report markdown here>
REPORT_EOF
)"
```

If local mode: skip posting, print the report to console instead.

## Step 8: Final Summary to User

After saving and posting, tell the user:
- The report has been saved locally (with path)
- If PR: the report has been posted to PR #X (with link)
- Quick stats: X critical, Y high, Z medium, W low
- The overall verdict (merge / don't merge)

---

## Aspect Filtering

If `$ARGUMENTS` contains keywords, only launch matching agents:
- `code` → code-reviewer
- `comments` → comment-analyzer
- `tests` → pr-test-analyzer
- `errors` or `silent` → silent-failure-hunter
- `types` → type-design-analyzer
- `docs` → docs-impact-agent
- `all` or empty → all 6 agents

Multiple keywords can be combined: `code errors types` launches 3 agents.

---

## Key Rules

- You do NOT review code yourself — delegate everything to sub-agents
- You MUST launch agents in parallel (single message with multiple Agent calls)
- You MUST wait for all agents before compiling
- You MUST save the report locally (always)
- You MUST post the report to the PR (unless local mode)
- You MUST use the exact report structure above — no improvising
- Keep the report concise — table cells should be 1-2 sentences max
