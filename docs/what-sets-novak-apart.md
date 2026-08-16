# What sets Novak apart

There are many self-hosted AI assistant projects, several of them more polished
than this one. This explains what's actually different, so you can decide
whether the differences are worth the extra assembly.

Written plainly. If a claim here can't be pointed at a file or a decision,
it shouldn't be here.

## 1. Nothing owns the system

Every part is replaceable. The model server, the chat UI, memory, the
knowledge base, and the voice pipeline are separate services, and every client
talks to the same ones. Delete any single piece and the rest keeps working.

This sounds like architecture pedantry until you watch it pay off. During one
week of building this:

- **OpenMemory**, the memory system this was originally built on, was
  deprecated and shut down by its authors.
- **Zep Community Edition**, a candidate replacement, turned out to be
  discontinued too.
- Three separate projects evaluated for other jobs — Tater, Letta, and
  home-generative-agent — each wanted to own the conversation loop and bring
  their own memory.

Replacing the memory layer meant swapping one service and writing one adapter.
Nothing else changed. In an all-in-one platform, an upstream shutdown like that
is a migration; here it was an afternoon.

The cost is real: more moving parts, more to configure, no single polished app
to point at. That trade is the entire project.

## 2. Memory isolation is structural, not a rule

Most memory integrations let the model say whose memories to fetch —
`search_memories(user="tyler")`. That's normal, and it's unsafe once a model
reads anything it didn't write: an email, a web page, a calendar entry. To a
model, a document saying *"look up user alice"* is just more text suggesting
what arguments to use.

Here, identity comes from the connection, not from the model. The tool has no
user parameter to poison. The server object is rebuilt per request with one
person's id baked in, so the tools physically cannot refer to anyone else.

The isolation isn't a check that could be removed by a careless edit — it's the
absence of any way to express the request. See
[how-memory-works.md](how-memory-works.md).

## 3. The admin UI can configure the stack but has no power over it

The console can add and remove integrations. It does this by writing a file
that a separate host-side script applies. It has no access to Docker.

This matters because anything able to create a container can create one with
full access to the machine — there's no safe way to grant "create a container"
to a web app. So the web app never gets it. Break into the console and you can
write a YAML file; that's the ceiling. And because that file is in git, every
change is reviewable and revertible.

## 4. Powerful things are allowed, but must be accepted on the record

Integrations are tagged `standard`, `elevated`, or `dangerous`. Anything above
standard won't start until someone writes down what it can do, who accepted
that, and when. Turning it back off takes nothing.

It's not a ban list, and it's not a warning dialog you click through. It's a
record that survives you forgetting. The reconciler reprints accepted risks on
every run so a decision from six months ago doesn't quietly become invisible.

## 5. What the assistant knows is readable and correctable

Knowledge lives in Outline — an ordinary wiki you can read, search, and fix.
Memories are rows in a database with a UI over them. Neither is an opaque
vector blob you can only interrogate by asking the model and hoping.

If the assistant believes something wrong about you, you go and correct it,
the same way you'd fix a wrong note.

## 6. It refuses to fake what it can't do

Voice does not identify who's speaking, because a microphone can't. Speaker
identification exists and works reasonably, but it produces a *guess* embedded
in the transcript text — which means anyone who says the right words can claim
to be someone else.

So voice gets one shared household memory, and personal memory stays behind
real authentication. A worse-looking feature, chosen because the better-looking
one would be lying.

## 7. Local weights, and an honest account of what that does and doesn't buy

Conversations are computed on your own hardware. There is no vendor channel, so
they cannot end up in someone's training data.

What that doesn't fix: credentials in the wrong place, tools with more power
than they need, and instructions hidden in content the model reads. Those are
the risks that remain, and they're what [security.md](security.md) is about.
Running locally is one guarantee, not a general safety property.

## 8. The reasoning is written down

[decisions.md](decisions.md) records every significant choice — what was
decided, why, what it cost, and what would justify changing it. Including the
ones that were reversed and the alternatives that were rejected.

This exists because the failure mode of a personal project is looking at your
own configuration in a year and having no idea why it's like that.

## What this is not

- **Not turnkey.** There's no one-click install. Setup is a checklist.
- **Not a product.** No support, no roadmap, no upgrade path but your own.
- **Not smart about models.** You pick two models by hand and clients choose a
  profile. Nothing routes by difficulty.
- **Not novel technology.** Almost all of it is other people's software —
  see [credits.md](credits.md). What's here is the wiring and the decisions.
- **Not, at time of writing, running.** None of this has been deployed.
