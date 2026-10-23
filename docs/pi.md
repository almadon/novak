# Coding with Pi

[Pi](https://pi.dev) is a minimal terminal coding agent (MIT). It reads and edits files and runs
commands in the directory you start it in, so it belongs in a terminal next to the code, not in
Open WebUI (the `Code` preset there is for snippets and review).

## Set it up

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent     # installs `pi`
novak pi config > ~/.pi/agent/models.json                           # the Novak router as a provider
export ROUTER_API_KEY=...                                            # `novak secret show ROUTER_API_KEY`
pi --append-system-prompt "$(novak pi hint)" --model novak/chat
```

`models.json` holds no key: it says `$ROUTER_API_KEY` and Pi reads the environment. On a machine
that is not Spire, run `novak pi config` on Spire and copy the output, or pass `--url`. Hosted
providers (Anthropic, OpenAI and others) can be added to the same file for work that should not
use the local models; that is a decision about where your code goes, not a Novak setting.

## What to expect from the local models

Checked on 2026-10-23 against the 14B `chat` model at an 8,192-token window:
- A small task (create a file and run it) took 4 seconds.
- A rename across a 150-line file looped for minutes with no help: Pi's `edit` tool needs the old
  text to match in exactly one place, the model kept sending text that matched twenty, and it never
  switched to `sed`. With the four lines in `prompts/novak-pi.md` the same task took 4 seconds.
  That is why `novak pi hint` exists. Expect to add a rule when you see a loop like this.
- The window is the real limit: every file Pi reads stays in it. Keep tasks small, and use a
  hosted model for work that spans many files. The larger `deep` model needs most of the GPU, so
  loading it for a coding session evicts the small model Home Assistant voice uses, and the next
  spoken request waits for it to load again.

Decision #73 has the reasoning.
