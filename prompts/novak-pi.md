# Novak — coding with Pi

Editing rules for Pi (the terminal coding agent) when it runs on a local model through the Novak
router. Pass it with `pi --append-system-prompt "$(cat prompts/novak-pi.md)"`, or `novak pi hint`
prints the same text. A real run showed why it exists: on a rename across a file, the 14B model
sent the same ambiguous `edit` about a hundred times, because the edit tool only accepts text that
matches in one place. With these four lines the same task took four seconds.

---

Editing rules for this session:
- The edit tool only works when oldText matches exactly ONE place in the file. If the same text
  appears more than once, do not repeat the edit: it will fail again.
- To rename or change something that appears many times, use bash instead, for example
  `sed -i '' 's/old_name/new_name/g' file.py` on macOS or `sed -i 's/old_name/new_name/g' file.py`
  on Linux. Then check the result with grep.
- If a tool call fails twice in the same way, stop and change your approach.
- Keep each step small: the context window is 8,192 tokens, and every file you read stays in it.
