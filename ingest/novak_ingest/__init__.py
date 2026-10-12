"""Novak ingest: recordings in, notes and proposed tasks out (decision #57).

Hardware-agnostic. A recorder, or an adapter that talks to one, hands this
service an audio file; it transcribes, summarises, writes a note, and proposes
tasks for a person to approve. It only does that work when nobody is using the
models, because chat and voice always come first.
"""
