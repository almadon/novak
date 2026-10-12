# Ingest: recordings in, notes and proposed tasks out

An optional extension (decision #57). A voice recorder, or a small adapter
that talks to one, hands this service an audio file. It transcribes the audio,
summarises it, writes a note, and proposes tasks for a person to approve.

It knows nothing about any particular recorder. The first one in mind is an
Omi wearable, but anything that can produce an audio file and a start time
works: a BLE puller, a phone share sheet, a script, a folder on a share.

## The rule that shapes it: passive work yields

Transcription and summarising are passive. Open WebUI chat and Home Assistant
voice are active. Active always wins, so this service starts a unit of work
only when no model has been used for a quiet window (180 seconds by default).

- **Units are small.** One chunk of about 60 seconds of audio, or one model
  call. Between units it checks again, so it stops within one unit of someone
  starting to chat. Progress is saved after every unit, so nothing is redone.
- **The probe** asks Ollama which models are loaded and when each was last
  used (`expires_at` minus the keep-alive). Its own calls are subtracted,
  otherwise finishing one summary would make the box look busy for the next
  three minutes. VERIFY: that `expires_at` moves at the end of a request as
  assumed. `docker exec novak-ingest-1 python -m novak_ingest idle` prints
  what the probe sees right now; check it before and after a chat turn.
- **Summaries use the `chat` role, not `deep`.** `chat` is already resident.
  Loading the 27B `deep` model evicts the chat and task models (decision #56),
  which would make the next Open WebUI turn pay a reload. Change `summary.role`
  in `registry/ingest.yaml` if you accept that.
- **Whisper runs on the CPU, at the lowest CPU share**, so it cannot compete
  with the GPU model for the card's 16 GB. Spire has a 6-core Ryzen 5600X, so
  a recording takes some multiple of its length to transcribe. VERIFY: measure
  it (see "First run"). That is fine for batch work nobody is waiting on.

## What it does with a recording

1. Keeps one copy of the audio, named by its SHA-256. A repeat upload is
   recognised and not processed twice.
2. Finds the silences with ffmpeg and cuts about every 60 seconds at a silence,
   so words are not split.
3. Transcribes each chunk with whisper.cpp, with timestamps.
4. Summarises: title, summary, key points, decisions, people, and tasks.
   Long transcripts are summarised in parts, then combined. The transcript is
   framed as untrusted: speech near a microphone can contain sentences that
   sound like instructions, and the model is told to report them, not follow them.
5. Writes a Markdown note to `/data/notes/<id>.md` (always), and sends it to any
   enabled sinks (Outline, Hindsight).
6. Stores each task as a **proposal** and tells you through Home Assistant.
   Nothing is written to a task tracker until a person approves it. A sink that
   fails never fails the recording: the note is already on disk.

Not built: speaker diarization (who said what). whisper.cpp offers stereo and
tinydiarize modes only; real diarization is a later step.

## Sending audio in

Any audio ffmpeg can read (Ogg Opus, WAV, MP3, M4A, FLAC). Over HTTP:

```bash
curl -X POST http://<host>:13409/v1/recordings \
  -H "Authorization: Bearer $INGEST_TOKEN" \
  -H "X-Source: omi" -H "X-Recorded-At: 1760000000" -H "X-Filename: a.opus" \
  --data-binary @a.opus
```

`X-Recorded-At` is Unix seconds or ISO 8601 (default: now). `X-Source` is a free
label (default `unknown`). The reply is `201 {"id": 7, "duplicate": false}`, or
`200` with `duplicate: true`. The size limit is `INGEST_MAX_UPLOAD_MB` (512).

Or drop the file in the `inbox` folder of the data volume. It is picked up once
it stops changing. An optional `<name>.json` beside it may carry
`{"source": "...", "recorded_at": "..."}`.

For an adapter that reads a device with segments (like the Omi storage sync),
upload each segment as its own recording, and only tell the device the data is
safe to free after the upload returns 200 or 201.

Also: `GET /v1/recordings`, `GET /v1/recordings/<id>`,
`GET /v1/proposals?status=pending`, `POST /v1/proposals/<id>/approve`, and
`.../reject`. All of `/v1` needs the bearer token.

## Approving tasks

- **Home Assistant notification (first channel).** Set `INGEST_HA_TOKEN` (a
  long-lived token) and `INGEST_HA_NOTIFY_TARGET` (a notify service such as
  `mobile_app_pixel`). The notification's action opens a review page with
  Approve and Reject buttons. The link carries an unguessable token and works
  without a login; the port is meant to be tailnet-only (`INGEST_BIND`).
  VERIFY: the action URL on a real phone.
- **The API** above, which is what the console would use. The console has not
  been evaluated yet; when it is, a proposals view can sit on this API, and a
  PWA install could add push. Nothing here is the only way to approve.
- If a task sink fails when you approve, the proposal stays pending so you can
  try again.

## Setting it up

1. In `.env` (`novak config`): `INGEST_ENABLED=true`, `INGEST_BIND=<Tailscale
   IP>`, and a token: `novak secret set INGEST_TOKEN --generate`.
2. Fetch a Whisper model into the models volume, once:
   `docker compose run --rm --no-deps --entrypoint download-ggml-model.sh stt large-v3-turbo-q5_0 /models`
   (VERIFY the script's arguments against the image you pulled).
3. `novak up`. The first run builds the `ingest` image (Python plus ffmpeg).
4. Check what it sees: `docker exec novak-ingest-1 python -m novak_ingest idle`.
5. Optional sinks, in `registry/ingest.yaml` (the deployed copy under
   `NOVAK_HOME/registry`). All three ship disabled because their tool names
   are guesses until checked against the live server:
   `docker exec novak-ingest-1 python -m novak_ingest mcp-tools <url> <TOKEN_ENV>`
   lists them. Set the URL variables in `.env`, correct `tool` and `args`,
   then `enabled: true`.

## First run: what to measure

- Seconds of CPU per minute of audio for the model you chose, with the chat
  models loaded and idle, and during a chat turn.
- Whether a chat turn started mid-transcription feels slower. If it does,
  lower `INGEST_STT_THREADS` or raise `idle.quiet_s`.
- The idle probe's output before and after a chat turn.
- Whisper on the GPU through Vulkan (`ghcr.io/ggml-org/whisper.cpp:main-vulkan`
  exists; set `INGEST_STT_IMAGE` to its digest). Not measured. It needs a
  spare gigabyte or two of VRAM next to the resident models, and Ollama does
  not know it is there, so a model load could fail. Treat it as an experiment.

## Files

| Path | What |
|---|---|
| `ingest/novak_ingest/` | The service (Python standard library, plus PyYAML) |
| `ingest/Dockerfile` | Python and ffmpeg, pinned by digest |
| `registry/ingest.yaml` | Behaviour: idle window, chunking, summary role, sinks |
| `ingest/tests/` | `python -m unittest discover -s tests` from `ingest/` |
