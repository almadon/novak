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

This service does wake-word detection **on the mini**, which is right for
Wyoming satellites and any mic streaming audio to Home Assistant.

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
2. **HA Voice PE hardware** — on-device microWakeWord. Model goes into the
   device's ESPHome config, and getting it there costs more than a file copy.
3. **Both** — two models, trained separately, sharing only the phrase.

## Training a microWakeWord model (for Voice PE)

Apple Silicon has a native trainer, so this runs on the mini itself:
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

It produces `trained_wake_words/hey_novak.tflite` and a matching `.json`
manifest. The JSON is what ESPHome consumes.

### Getting it onto the device — cost depends entirely on which device

ESPHome's `micro_wake_word` accepts a custom model:

```yaml
micro_wake_word:
  models:
    - model: /config/models/hey_novak.json
      id: hey_novak
      probability_cutoff: 0.95
```

**On HA Voice PE this is the expensive part.** It ships stock firmware, so
changing its models means adopting the device in ESPHome Builder and flashing
your own build — leaving the stock update path and owning that firmware from
then on.

**On a FutureProofHomes Satellite 1 it is not.** Its firmware is
[open source ESPHome](https://github.com/FutureProofHomes/Satellite1-ESPHome)
that you are expected to build yourself; the vendor documents compiling your own
with additional microWakeWords and points at the same author's model collection.
Nothing is given up by customising it, because customising it is the supported
path. It also has an XMOS chip doing echo cancellation and beamforming *before*
detection, so the model sees a cleaner signal than a bare microphone gives.

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
