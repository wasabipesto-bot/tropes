from types import SimpleNamespace

from tropes_worker.jobs.transcribe import cues_from_segments, wants_transcript


def test_only_video_misses_are_transcribed():
    assert wants_transcript({"kind": "video", "indexedAt": "2026-10-26", "meta": {"textSource": "none"}})
    assert not wants_transcript({"kind": "video", "indexedAt": "2026-10-26", "meta": {"textSource": "sidecar"}})
    assert not wants_transcript({"kind": "video", "indexedAt": None, "meta": {}})
    assert not wants_transcript({"kind": "book", "indexedAt": "2026-10-26", "meta": {"textSource": "none"}})


def test_segments_become_cues_without_noise_lines():
    segs = [
        SimpleNamespace(start=1.0, end=2.5, text=" We're  almost there. "),
        SimpleNamespace(start=3.0, end=3.5, text="[music]"),
        SimpleNamespace(start=4.0, end=4.2, text="   "),
        SimpleNamespace(start=5.0, end=6.0, text="Keep going."),
    ]
    cues = cues_from_segments(segs)
    assert [(c.start, c.text) for c in cues] == [(1.0, "We're almost there."), (5.0, "Keep going.")]
