# Agentrace

**Observability for AI agent sessions.**

When your team starts using AI agents seriously — skills, hooks, knowledge trees,
context files — you eventually ask: *is any of this actually working?*

Agentrace answers that. It logs what context was loaded, how many tokens it cost,
which skills fired, and what the session produced. Over time you can prove that
your knowledge tree reduced context load by 60%, or that a new skill cut average
session token usage in half.

It's an audit log for the AI layer of your workflow.

---

## The Problem

When you move a team to AI-assisted workflows, you make bets:

- "This skills library will make agents more consistent."
- "This knowledge tree will reduce how much context we load."
- "These hooks will keep docs up to date automatically."

Right now those are gut feelings. You can't show the numbers. When someone asks
*"is this AI stuff actually making us better?"*, you're guessing.

Agentrace makes those bets measurable.

---

## What It Tracks

| Signal | Why it matters |
|--------|---------------|
| **Context files loaded** | Proves a leaner knowledge tree loads less |
| **Token counts (in/out)** | Hard numbers on context cost per session |
| **Skills fired** | Which skills are being used, which aren't |
| **Session outcomes** | What was produced, what was committed |
| **Before/after comparisons** | Show improvement when you optimize context |

---

## Use Cases

**Proving context reduction to skeptics**
Before: agent loads 12 files, 42k tokens. After knowledge tree refactor: 4 files,
8k tokens. Same quality outcome. That's a measurable argument.

**Skills library adoption tracking**
Which skills does your team actually use? Which are dead weight?
Agentrace shows you what fires and what doesn't.

**Debugging agent behavior**
"Why did the agent make that decision?" → look at what context it had access to.

**Benchmarking knowledge tree improvements**
Make a change to your context structure. Run the same task before and after.
Compare the traces. Iterate.

---

## Status

Early scaffold. The vision is clear; the implementation is next.

See `docs/VISION.md` for product thinking and roadmap.
