"use client";
import { useState } from "react";

const MAX = 4000;

/** The text box, with a running count. The server enforces the limit; this only helps you stay under it. */
export function Editor({ person, initial, action }: { person: string; initial: string; action: (f: FormData) => Promise<void> }) {
  const [text, setText] = useState(initial);
  const over = text.trim().length > MAX;
  return (
    <form action={action} className="stack">
      <input type="hidden" name="person" value={person} />
      <label htmlFor="text" className="label">Standing instructions for {person}</label>
      <textarea id="text" name="text" value={text} onChange={(e) => setText(e.target.value)} rows={22} spellCheck />
      <div className="row">
        <span className={over ? "meta danger" : "meta"}>
          {text.trim().length} of {MAX} characters, about {Math.ceil(text.length / 4)} tokens. Aim for about 250 tokens: the local models have a small window.
        </span>
        <button type="submit" className="button" disabled={over || text.trim() === ""}>Save</button>
      </div>
    </form>
  );
}
