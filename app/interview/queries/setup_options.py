# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Cascaded setup options from the theory and coding banks."""

from collections.abc import Callable

from app.interview.schemas.setup import SetupOptionsRead
from app.shared import coding as coding_bank
from app.shared.questions import list_categories, list_levels, list_tracks


class UnknownSetupOptionError(LookupError):
    """Raised when a requested track or level is not present in the bank."""


def theory_options(
    track: str | None = None,
    level: str | None = None,
) -> SetupOptionsRead:
    """Return cascaded theory options for the setup form.

    Args:
        track: When set, returns levels for that theory track.
        level: When set with ``track``, returns categories for that pair.

    Returns:
        Options response carrying ``tracks``, ``levels`` or ``categories``.

    Raises:
        UnknownSetupOptionError: If the track or level slug is unknown.
    """
    return _cascade(
        track,
        level,
        list_tracks_fn=list_tracks,
        list_levels_fn=list_levels,
        list_categories_fn=list_categories,
        unknown_track="Unknown track",
        unknown_level="Unknown level",
    )


def coding_options(
    track: str | None = None,
    level: str | None = None,
) -> SetupOptionsRead:
    """Return cascaded coding options for the setup form.

    Args:
        track: When set, returns levels for that coding track.
        level: When set with ``track``, returns categories for that pair.

    Returns:
        Options response carrying ``tracks``, ``levels`` or ``categories``.

    Raises:
        UnknownSetupOptionError: If the track or level slug is unknown.
    """
    return _cascade(
        track,
        level,
        list_tracks_fn=coding_bank.list_tracks,
        list_levels_fn=coding_bank.list_levels,
        list_categories_fn=coding_bank.list_categories,
        unknown_track="Unknown coding track",
        unknown_level="Unknown coding level",
    )


def _cascade(
    track: str | None,
    level: str | None,
    *,
    list_tracks_fn: Callable[[], list[str]],
    list_levels_fn: Callable[[str], list[str]],
    list_categories_fn: Callable[[str, str], list[str]],
    unknown_track: str,
    unknown_level: str,
) -> SetupOptionsRead:
    """Walk the track → level → category cascade for one bank."""
    if track is None:
        return SetupOptionsRead(tracks=list_tracks_fn())

    if track not in list_tracks_fn():
        raise UnknownSetupOptionError(f"{unknown_track}: {track}")

    if level is None:
        return SetupOptionsRead(levels=list_levels_fn(track))

    if level not in list_levels_fn(track):
        raise UnknownSetupOptionError(f"{unknown_level}: {level}")

    return SetupOptionsRead(categories=sorted(list_categories_fn(track, level)))
