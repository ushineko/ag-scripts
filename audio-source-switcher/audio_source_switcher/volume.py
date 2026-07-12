"""Shared smart-volume logic.

Resolving the physical sink to control is JamesDSP-aware: when the system default
is ``jamesdsp_sink``, the real target is whatever hardware sink JamesDSP is routed
to. Both the in-app OSD path and the CLI fallback use these helpers so the logic
lives in exactly one place.
"""

from audio_source_switcher.controllers.audio import AudioController
from audio_source_switcher.controllers.pipewire import PipeWireController


def resolve_active_sink(audio: AudioController, pw: PipeWireController) -> str | None:
    """Return the physical sink we should control, following JamesDSP routing."""
    default = audio.get_default_sink()
    if default == "jamesdsp_sink":
        hw_target = pw.get_jamesdsp_target()
        if hw_target:
            return hw_target
    return default


def adjust_volume(
    audio: AudioController,
    pw: PipeWireController,
    direction: str,
    step: int = 5,
) -> tuple[str | None, int | None, bool]:
    """Apply a relative volume step to the active (smart-resolved) sink.

    Returns ``(target_sink, new_volume_percent, muted)``. ``target_sink`` is None
    when no sink could be resolved.
    """
    target = resolve_active_sink(audio, pw)
    if not target:
        return None, None, False

    audio.step_sink_volume(target, direction, step)
    new_vol = audio.get_sink_volume(target)
    muted = audio.get_sink_mute(target)
    return target, new_vol, muted
