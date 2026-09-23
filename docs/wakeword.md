# "Hey Novak" wake word

The `openwakeword` service in the compose file loads custom models from
this directory (`wakeword/models/`, mounted at `/custom`). Drop a trained
model in, restart the service, and it appears in Home Assistant's Voice
assistants settings.

## Choose the phrase: "Hey Novak", not "Novak"

Home Assistant's guidance is 3–4 syllables for a wake word — "Novak" alone
is two, and short phrases false-trigger constantly on ordinary speech.
Use **"hey novak"** (or "ok novak"). The assistant is still named Novak;
the wake phrase is just how you address it.

This is not a style preference, and it gets stronger the shorter you go. A
wake-word model decides from a fixed, very short window of audio; fewer
syllables mean less to distinguish the phrase from everything else a room
produces. Truncations are the worst case — **"hey no" is not a viable wake
word.** It sits inside ordinary speech ("hey, no —", "hey, Noah", "hey, you
know"), so no `probability_cutoff` separates it: lower and the television
wakes it, higher and it stops hearing you. Shortening the phrase to make
detection cheaper trades away the only thing detection has to work with.

## Training a model

openWakeWord trains from synthetic speech — no recording sessions, no ML
knowledge:

- **Home Assistant's official flow**: <https://www.home-assistant.io/voice_control/create_wake_word/>
  — a Colab notebook that generates clips with Piper and trains the model.
- **openwakeword.com** — a hosted trainer, if you'd rather not run the
  notebook.

Name the output file for the phrase (`hey_novak.tflite`) — the filename
becomes the wake word identifier in Home Assistant, so a generic name is
a future headache. Put it in `models/` here.

English only: openWakeWord doesn't yet have multi-speaker models for other
languages.

## Important: this covers server-side detection only

This service does wake-word detection **on whichever host runs the
stack** (Spire, decision #33), which is right for Wyoming satellites and
any mic streaming audio to Home Assistant.

**Home Assistant Voice PE hardware detects its wake word on-device using
microWakeWord**, a different system with a different model format. A model
trained here for openWakeWord will not run on it, and vice versa. If you want
"Hey Novak" in both places, you train it twice.

That situation has improved since this was first written — custom
microWakeWord training is now possible, and possible on a Mac. See
[Training a microWakeWord model](#training-a-microwakeword-model-for-voice-pe)
below.

Decide which you need before training anything:

1. **Wyoming satellites, or any mic streaming audio to HA** — server-side, this
   openWakeWord service. Model goes in `models/` here.
2. **HA Voice PE hardware** — on-device microWakeWord. Model is committed to
   `microwakeword/` here (source of truth, same as `models/` above), then
   separately copied onto the device's own ESPHome config — that second
   step costs more than a file copy.
3. **Both** — two models, trained separately, sharing only the phrase.

## Training a microWakeWord model (for Voice PE)

Apple Silicon has a native trainer, so this runs on a Mac:
<https://github.com/TaterTotterson/microWakeWord-Trainer-AppleSilicon>

Prerequisites: an Apple Silicon Mac, `python@3.11`, and `ffmpeg`. No Docker.

```bash
git clone https://github.com/TaterTotterson/microWakeWord-Trainer-AppleSilicon.git
cd microWakeWord-Trainer-AppleSilicon
./run.sh                      # sets up a venv, serves a UI on 127.0.0.1:8789
```

or headless:

```bash
./train_microwakeword_macos.sh "hey_novak"
```

It produces `trained_wake_words/hey_novak.tflite` plus JSON manifests. The
trainer writes two, one a strict subset of the other: a full one carrying
its own training and calibration metadata (including a `tater_native` block
for that project's own satellite firmware, and the trainer's name as
`author`), and a minimal one holding only what ESPHome's `micro_wake_word:`
reads. ESPHome needs one manifest, in the same schema as the stock models,
so this repo keeps a single `hey_novak.json` in that schema (decision #51),
with the trainer credited in [credits.md](credits.md) rather than in the
model's own `author` field.

Put the `.tflite` and that one manifest in
[`microwakeword/`](../wakeword/microwakeword/) here and commit them, same
reasoning as `models/` above: a trained model is a build output worth
versioning, not a file that only ever exists on whichever machine happened
to train it. Training is also genuinely hard to reproduce exactly
(nondeterministic, and "still very difficult" per the upstream trainer's own
warning below), so the committed copy is the only reliable way back to it
if the local output ever gets lost. The trainer's calibration numbers are
recorded in decision #43; the original full manifest is in git history.

A real training run completed 2026-09-19. The model exists and is versioned
in this repo; it has not been compiled into firmware or heard by a real
device yet.

### Getting it onto the device — cost depends entirely on which device

Committing the model here (above) is the versioning step, not the
deployment step. ESPHome's `micro_wake_word` takes a custom model as a
manifest path or URL, and resolves the `.tflite` relative to it, so a raw
URL into this (public) repo works without copying anything onto the device:

```yaml
micro_wake_word:
  models:
    - id: hey_novak
      model: https://raw.githubusercontent.com/almadon/novak/main/wakeword/microwakeword/hey_novak.json
```

`main` moves; pin the URL to a commit SHA once a model is proven on a device,
for the same reason images are pinned to digests (decision #45).

**On HA Voice PE this is the expensive part.** It ships stock firmware, so
changing its models means adopting the device in ESPHome Builder and flashing
your own build — leaving the stock update path and owning that firmware from
then on.

**On a FutureProofHomes Satellite 1 it is not.** Its firmware is
[open source ESPHome](https://github.com/FutureProofHomes/Satellite1-ESPHome)
that you are expected to build yourself; the vendor documents compiling your own
with additional microWakeWords. Nothing is given up by customising it, because
customising it is the supported path. It also has an XMOS chip doing echo
cancellation and beamforming *before* detection, so the model sees a cleaner
signal than a bare microphone gives.

Read against Satellite1-ESPHome v0.2.1's own `satellite1.dashboard.yaml`
and `common/voice_assistant.yaml` (not yet compiled or flashed, so VERIFY
on the device):

- Its documented custom-model pattern is the `models:` list above, under the
  existing `micro_wake_word: id: mww`, added alongside the stock entries.
  Add `- id: !remove hey_jarvis` to drop the default word.
- **The "Wake word sensitivity" selector does not apply to `hey_novak`.** Its
  lambda sets cutoffs only for the models built into the firmware
  (`okay_nabu`, `hey_jarvis`), calibrated by FPH against their own corpus.
  `hey_novak` runs at its manifest's `probability_cutoff` (0.99, from the
  trainer's own, different validation set) until you change it. Removing a
  stock model that the lambda still names, such as `hey_jarvis`, breaks the
  compile unless the selector is removed too, as the firmware's own comment
  says.
- FPH's stock manifests use cutoffs of 0.85 (`okay_nabu`) and 0.97
  (`hey_jarvis`); `okay_nabu`'s `tensor_arena_size` is 37000, while this
  model's manifest says 30000 (from the trainer). If the device logs a
  tensor arena allocation failure, raise it first.

### Why on-device usually beats this service

Where the hardware supports it, on-device detection is the better arrangement,
and not marginally:

- **Nothing streams until the wake word fires.** openWakeWord needs a continuous
  audio stream to the mini; microWakeWord sends nothing until it triggers. Less
  network, less server work, and audio stays in the room until you address it —
  which fits the rest of this project's reasoning better than the alternative.
- **Detection stops depending on the mini.** With server-side detection, a
  restart here means satellites cannot even hear their name.
- **The latency budget starts later.** Detection is not competing with the
  network hop for the 1–2s a spoken reply has.

So this openWakeWord service is for microphones that *cannot* detect on-device —
generic Wyoming satellites, a phone, anything streaming raw audio. If every
satellite you own does it on-device, this container has no work to do.

`probability_cutoff` is where a home-trained word lives or dies: too low and it
triggers on the television, too high and it ignores you. Expect to tune it, and
expect the upstream warning to apply — *"training a model that works well is
still very difficult"*. A stock word on Voice PE plus "Hey Novak" on streaming
satellites is a legitimate place to stop.
