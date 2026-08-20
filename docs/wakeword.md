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
microWakeWord**, which ships pre-trained words ("okay nabu", "hey jarvis",
"hey mycroft") and does *not* support custom training the way openWakeWord
does. So on Voice PE, "Hey Novak" is not currently a drop-in option — your
choices are:

1. Keep a stock wake word on the Voice PE hardware (it's just the trigger;
   the assistant still identifies as Novak when it answers).
2. Use satellites that stream to this openWakeWord service instead.
3. Watch the community microWakeWord model collection — people have
   contributed custom-trained words there, and the situation may have
   improved since this was written.

Decide this before training anything, since it determines whether the
trained model is usable on your hardware.
