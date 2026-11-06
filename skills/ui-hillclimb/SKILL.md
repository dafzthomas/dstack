---
name: ui-hillclimb
description: Polish an app's UI by hill climbing against a council of reviewer models from different providers. Each round they score the same screenshots of one commit, next to reference apps, by design category; you fix what you agree with, then rescore until every reviewer puts the app at the target and level with or ahead of every reference app in every category. Use when explicitly asked for a UI hill climb, a council design review, or to make a UI score a target such as 9/10 against named apps.
---

# UI hill climb

Design quality can't be checked by a program, but scores from several strong models can stand in for one. One model's score is noisy, and a high score from every reviewer at once is hard to fake. Climb that: capture screenshots, get scores, fix, and score again.

## Before round 1

Settle these with the user, then start:

- **Target.** Use the user's score, or 9/10 if they gave none.
- **Reference apps.** Two or three apps the user wants to beat, with the user's screenshots of the same screens in them. You usually can't capture another app yourself. Scoring the app alone inflates its scores: one PR that scored 9/10 on its own scored 7.4 once reference apps were in the same review.
- **Budget.** A maximum number of rounds and, if the user has one, a spend limit. Going from 9 to 9.5 once took ten extra rounds.
- **Council.** One strong model from each of three providers, at `xhigh` effort. Two providers is the minimum. If fewer than two are available, or a model the user named isn't, tell the user and stop. Don't substitute a model. Reviewers are always delegates. The model running this loop never scores its own work.

Then prepare:

- **Capture script.** Write or reuse a script that captures a fixed screenshot set from the running app, so every round captures the same screens at the same window size, with the same data. Include the main working view, a busy state, an empty state, settings, dialogs or menus, and light and dark mode. Don't capture splash or loading screens. Save each round's captures to `/tmp/ui-hillclimb/<round>/` and the user's reference screenshots to `/tmp/ui-hillclimb/references/`.
- **Categories.** Start with typography, color and contrast, spacing and rhythm, alignment, iconography, hierarchy and information density, consistency, craft and polish, light/dark parity, accessibility, and copy and voice. Add interaction states, responsive behavior or motion only if the set includes hover and focus captures, narrow-window captures or recordings to show them.
- **Branch.** Work on a new branch with its own PR. Capture `main` once as round 0.

## Each round

1. **Capture.** Commit the changes, record the commit hash, and run the capture script. Typecheck, lint and run tests first.
2. **Brief each reviewer separately and in parallel,** as a fresh delegate. In T3 Code, resolve the models with `orchestrator_capabilities`, then call `delegate_task` once per reviewer with `role: "review"` and the default shared isolation. A delegate gets only the task text, so the brief must contain everything:
   - the commit hash, plus the absolute path of every round-0, current and reference screenshot, each labelled;
   - an instruction to stay read-only, and that it may read the diff and source;
   - the categories, scored from 1 to 10 to one decimal place, for this app and for each reference app;
   - an instruction to ignore differences in image quality between the captures;
   - for any score under 10, the screen and element behind it;
   - the highest-value changes, ranked;
   - from round 2 on, the fixes made since the last round, so it can check for regressions.

   Don't pass on the target, earlier scores or the other reviewers' answers. Theo suspected that knowing the goal raised scores. It's a guess, but hiding them costs nothing.

   Outside T3 Code, use the host's subagent tool if it can run models from other providers. If it can't, tell the user and stop.
3. **Collect** each reviewer's scores into the round's table, with the commit hash. If a reviewer gives no score, write `no score`, and if you didn't ask a reviewer this round, write `not run`. Never invent a score. Summarise where the reviewers disagree.
4. **Decide.** Make the changes you agree with. When reviewers agree, treat that as evidence, not an order. Decline anything that would add features, change product behaviour or undo a choice the user made, and record it as declined in the PR. Repeated reviews tend to pull in more and more changes. Your job is to keep the scope narrow.
5. **Fix,** then start the next round.

## Stopping

**Done.** Stop when, in one round on one commit, every reviewer scores this app at or above the target in every category, and at or above every reference app in each category. If a reviewer can't score a category, ask the user whether to drop it or add a capture that shows it.

**Budget.** Stop when you reach the maximum number of rounds or the spend limit.

**Stalled.** The reference screenshots never change, so any change in their scores between rounds is noise. If the app's lowest category score rises by less than that noise over two rounds, stop.

When you stop for the budget or a stall, report the categories still short and what the reviewers say is holding them back.

## Saving budget

Only if the user asks to save budget: run the cheapest reviewer alone until it clears the stop rule, then bring in the others. Climbing against one reviewer overfits to its taste, so the stop rule still needs every reviewer on the same commit.

## PR description

Keep this section up to date in the PR description by editing it, not by posting comments. If there is no PR, put it in your final reply.

```markdown
## Council review

Rounds: 3. Lowest category score each round:

| Delegate | Round 1 (abc1234) | Round 2 (def5678) | Round 3 (0a1b2c3) |
| --- | --- | --- | --- |
| Claude Opus | 7.1 | not run | 9.0 |
| GPT (Codex) | 7.4 | 8.9 | 9.1 |

Final round, lowest score across delegates:

| Category | This PR | Reference A | Reference B |
| --- | --- | --- | --- |
| Typography | 9.2 | 8.8 | 9.0 |

Declined to hold scope: <asks you declined, and why>.
```

Add before-and-after screenshots with arrows and a one-line note on each change. They let a reviewer who isn't a designer see subtle changes such as font fallbacks, corner radii and contrast. `gh` can't upload images. If you have no other way to add them, list their paths and tell the user they need attaching.

## After the stop rule passes

Passing the stop rule is where the user's judgement starts, not where it ends. Show them the before-and-after screenshots and ask what still feels wrong. Taste notes such as "it's too grayscale now, bring some color back" go into the next pass. If they want to go further, stack a new branch on this PR, raise the target (9, then 9.5, then 10), and keep the existing PR mergeable while you do.

---

Pieced together from Theo's "Agents Sucked At UI (Until Today)" (youtube.com/watch?v=xq0eB8vxeqk, 2026-11-03), which shows his unpublished `council` skill and the prompts he used to drive it.
