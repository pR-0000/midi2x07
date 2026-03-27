#!/usr/bin/env python3

import argparse
import os
import struct
import sys
from bisect import bisect_right
from dataclasses import dataclass


DEFAULT_TEMPO_US = 500000
X07_LOW_MIDI = 60
X07_HIGH_MIDI = 107
X07_NOTE_MIN = 1
X07_NOTE_MAX = 48
SHORT_DURATIONS = (1, 2, 4, 8)


@dataclass
class MidiNote:
    start_tick: int
    end_tick: int
    note: int
    velocity: int
    channel: int
    track: int


@dataclass
class TempoPoint:
    tick: int
    tempo_us: int
    start_us: int


def read_u16_be(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def read_u32_be(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        if pos >= len(data):
            raise ValueError("VLQ tronque")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if (byte & 0x80) == 0:
            return value, pos


def sanitize_label(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    label = "".join(out)
    if not label or label[0].isdigit():
        label = "_" + label
    return label


def parse_track(track_data: bytes, track_index: int) -> tuple[list[MidiNote], list[tuple[int, int]], str]:
    pos = 0
    abs_tick = 0
    running_status = None
    active_notes: dict[tuple[int, int], tuple[int, int]] = {}
    notes: list[MidiNote] = []
    tempos: list[tuple[int, int]] = []
    track_name = f"track_{track_index}"

    while pos < len(track_data):
        delta, pos = read_vlq(track_data, pos)
        abs_tick += delta
        if pos >= len(track_data):
            break

        status = track_data[pos]
        if status < 0x80:
            if running_status is None:
                raise ValueError(f"Running status invalide sur piste {track_index}")
            status = running_status
        else:
            pos += 1
            if status < 0xF0:
                running_status = status
            else:
                running_status = None

        if status == 0xFF:
            if pos >= len(track_data):
                raise ValueError(f"Meta event tronque sur piste {track_index}")
            meta_type = track_data[pos]
            pos += 1
            length, pos = read_vlq(track_data, pos)
            payload = track_data[pos:pos + length]
            if len(payload) != length:
                raise ValueError(f"Meta payload tronque sur piste {track_index}")
            pos += length

            if meta_type == 0x2F:
                break
            if meta_type == 0x51 and length == 3:
                tempo_us = (payload[0] << 16) | (payload[1] << 8) | payload[2]
                tempos.append((abs_tick, tempo_us))
            elif meta_type == 0x03 and payload:
                try:
                    track_name = payload.decode("latin-1").strip() or track_name
                except UnicodeDecodeError:
                    pass
            continue

        if status in (0xF0, 0xF7):
            length, pos = read_vlq(track_data, pos)
            pos += length
            continue

        event_type = status & 0xF0
        channel = status & 0x0F

        if event_type in (0xC0, 0xD0):
            if pos >= len(track_data):
                raise ValueError(f"Event MIDI tronque sur piste {track_index}")
            pos += 1
            continue

        if pos + 1 >= len(track_data):
            raise ValueError(f"Event MIDI tronque sur piste {track_index}")

        data1 = track_data[pos]
        data2 = track_data[pos + 1]
        pos += 2

        if event_type == 0x90 and data2 != 0:
            key = (channel, data1)
            if key in active_notes:
                start_tick, velocity = active_notes[key]
                if abs_tick > start_tick:
                    notes.append(MidiNote(start_tick, abs_tick, data1, velocity, channel, track_index))
            active_notes[key] = (abs_tick, data2)
        elif event_type == 0x80 or (event_type == 0x90 and data2 == 0):
            key = (channel, data1)
            if key in active_notes:
                start_tick, velocity = active_notes.pop(key)
                if abs_tick > start_tick:
                    notes.append(MidiNote(start_tick, abs_tick, data1, velocity, channel, track_index))

    for (channel, note), (start_tick, velocity) in active_notes.items():
        if abs_tick > start_tick:
            notes.append(MidiNote(start_tick, abs_tick, note, velocity, channel, track_index))

    return notes, tempos, track_name


def parse_midi(path: str) -> tuple[int, list[MidiNote], list[tuple[int, int]], list[str]]:
    with open(path, "rb") as handle:
        data = handle.read()

    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("Ce fichier n'est pas un MIDI standard valide.")

    header_len = read_u32_be(data, 4)
    if header_len < 6:
        raise ValueError("Header MIDI invalide.")

    fmt = read_u16_be(data, 8)
    track_count = read_u16_be(data, 10)
    division = read_u16_be(data, 12)
    if division & 0x8000:
        raise ValueError("Le format MIDI SMPTE n'est pas pris en charge.")
    if fmt not in (0, 1):
        raise ValueError(f"Format MIDI {fmt} non pris en charge (attendu: 0 ou 1).")

    pos = 8 + header_len
    all_notes: list[MidiNote] = []
    tempos: list[tuple[int, int]] = [(0, DEFAULT_TEMPO_US)]
    track_names: list[str] = []

    for track_index in range(track_count):
        if pos + 8 > len(data):
            raise ValueError("Chunk MIDI tronque.")
        chunk_id = data[pos:pos + 4]
        chunk_len = read_u32_be(data, pos + 4)
        pos += 8
        payload = data[pos:pos + chunk_len]
        if len(payload) != chunk_len:
            raise ValueError("Payload de chunk MIDI tronque.")
        pos += chunk_len

        if chunk_id != b"MTrk":
            continue

        notes, track_tempos, track_name = parse_track(payload, track_index)
        all_notes.extend(notes)
        tempos.extend(track_tempos)
        track_names.append(track_name)

    return division, all_notes, tempos, track_names


def build_tempo_map(ticks_per_beat: int, tempo_events: list[tuple[int, int]]) -> tuple[list[TempoPoint], list[int]]:
    latest_by_tick: dict[int, int] = {}
    for tick, tempo_us in tempo_events:
        latest_by_tick[tick] = tempo_us

    ordered = sorted(latest_by_tick.items())
    if not ordered or ordered[0][0] != 0:
        ordered.insert(0, (0, DEFAULT_TEMPO_US))

    points: list[TempoPoint] = []
    start_us = 0
    prev_tick = ordered[0][0]
    prev_tempo = ordered[0][1]
    points.append(TempoPoint(prev_tick, prev_tempo, 0))

    for tick, tempo_us in ordered[1:]:
        start_us += ((tick - prev_tick) * prev_tempo) // ticks_per_beat
        points.append(TempoPoint(tick, tempo_us, start_us))
        prev_tick = tick
        prev_tempo = tempo_us

    return points, [point.tick for point in points]


def tick_to_us(tick: int, tempo_points: list[TempoPoint], tempo_ticks: list[int], ticks_per_beat: int) -> int:
    idx = bisect_right(tempo_ticks, tick) - 1
    if idx < 0:
        idx = 0
    point = tempo_points[idx]
    return point.start_us + ((tick - point.tick) * point.tempo_us) // ticks_per_beat


def choose_auto_transpose(notes: list[int]) -> int:
    if not notes:
        return 0

    best_shift = 0
    best_score = None
    for shift in range(-48, 49, 12):
        in_range = 0
        center_penalty = 0
        for note in notes:
            shifted = note + shift
            if X07_LOW_MIDI <= shifted <= X07_HIGH_MIDI:
                in_range += 1
            if shifted < X07_LOW_MIDI:
                center_penalty += X07_LOW_MIDI - shifted
            elif shifted > X07_HIGH_MIDI:
                center_penalty += shifted - X07_HIGH_MIDI
        score = (in_range, -center_penalty, -abs(shift))
        if best_score is None or score > best_score:
            best_score = score
            best_shift = shift
    return best_shift


def midi_to_x07(note: int, transpose: int, fold_octaves: bool) -> int | None:
    shifted = note + transpose
    if fold_octaves:
        while shifted < X07_LOW_MIDI:
            shifted += 12
        while shifted > X07_HIGH_MIDI:
            shifted -= 12
    if shifted < X07_LOW_MIDI or shifted > X07_HIGH_MIDI:
        return None
    return shifted - (X07_LOW_MIDI - 1)


def soften_high_x07_note(note_value: int, max_x07_note: int) -> int:
    while note_value > max_x07_note and note_value - 12 >= X07_NOTE_MIN:
        note_value -= 12
    return note_value


def reduce_to_mono(
    notes: list[MidiNote],
    ticks_per_beat: int,
    tempo_points: list[TempoPoint],
    tempo_ticks: list[int],
    priority: str,
    preferred_tracks: set[int] | None = None,
) -> list[tuple[int, int, int | None]]:
    if not notes:
        return []

    timeline = []
    for note_id, note in enumerate(notes):
        start_us = tick_to_us(note.start_tick, tempo_points, tempo_ticks, ticks_per_beat)
        end_us = tick_to_us(note.end_tick, tempo_points, tempo_ticks, ticks_per_beat)
        if end_us <= start_us:
            continue
        timeline.append((start_us, 1, note_id, note))
        timeline.append((end_us, 0, note_id, note))

    if not timeline:
        return []

    timeline.sort(key=lambda item: (item[0], item[1]))
    active: dict[int, MidiNote] = {}
    spans: list[tuple[int, int, int | None]] = []
    cursor_us = timeline[0][0]
    idx = 0

    while idx < len(timeline):
        time_us = timeline[idx][0]
        if time_us > cursor_us:
            chosen = None
            if active:
                chosen_note = choose_active_note(list(active.values()), priority, preferred_tracks)
                chosen = chosen_note.note
            spans.append((cursor_us, time_us, chosen))
            cursor_us = time_us

        group_end = idx
        while group_end < len(timeline) and timeline[group_end][0] == time_us:
            group_end += 1
        for event_idx in range(idx, group_end):
            _, kind, note_id, note = timeline[event_idx]
            if kind == 0:
                active.pop(note_id, None)
            else:
                active[note_id] = note
        idx = group_end

    return spans


def choose_active_note(active_notes: list[MidiNote], priority: str, preferred_tracks: set[int] | None = None) -> MidiNote:
    if preferred_tracks:
        preferred_notes = [item for item in active_notes if item.track in preferred_tracks]
        if preferred_notes:
            active_notes = preferred_notes

    if priority == "highest":
        return max(active_notes, key=lambda item: (item.note, item.velocity, -item.track, item.start_tick))

    if priority == "newest":
        return max(active_notes, key=lambda item: (item.start_tick, item.note, item.velocity, -item.track))

    if priority == "melody":
        ranked = sorted(
            active_notes,
            key=lambda item: (item.note, item.velocity, -item.track, item.start_tick),
            reverse=True,
        )
        shortlist = ranked[:3]
        return max(shortlist, key=lambda item: (item.start_tick, item.note, item.velocity, -item.track))

    raise ValueError(f"Strategie de reduction inconnue: {priority}")


def simplify_events(
    spans: list[tuple[int, int, int | None]],
    unit_ms: int,
    min_note_units: int,
    min_rest_units: int,
    merge_gap_units: int,
    smooth_units: int,
    transpose: int,
    fold_octaves: bool,
    max_x07_note: int,
    max_note_units: int,
    retrigger_gap_units: int,
    pseudo_poly: int,
    pseudo_poly_step_units: int,
) -> list[list[int]]:
    unit_us = unit_ms * 1000
    events: list[list[int]] = []

    for start_us, end_us, midi_note in spans:
        duration_units = int(round((end_us - start_us) / unit_us))
        if duration_units <= 0:
            continue

        if midi_note is None:
            note_value = 0
        else:
            mapped = midi_to_x07(midi_note, transpose, fold_octaves)
            note_value = 0 if mapped is None else soften_high_x07_note(mapped, max_x07_note)

        if note_value == 0 and duration_units < min_rest_units:
            continue
        if note_value != 0 and duration_units < min_note_units:
            continue

        events.append([note_value, duration_units])

    while events and events[0][0] == 0:
        events.pop(0)
    while events and events[-1][0] == 0:
        events.pop()

    if not events:
        return []

    events = merge_identical(events)

    if merge_gap_units > 0:
        idx = 1
        while idx + 1 < len(events):
            prev_note, prev_duration = events[idx - 1]
            gap_note, gap_duration = events[idx]
            next_note, next_duration = events[idx + 1]
            if gap_note == 0 and gap_duration <= merge_gap_units and prev_note == next_note and prev_note != 0:
                events[idx - 1][1] = prev_duration + gap_duration + next_duration
                del events[idx:idx + 2]
                continue
            idx += 1

    events = merge_identical(events)
    events = smooth_events(events, smooth_units)
    events = split_long_notes(events, max_note_units, retrigger_gap_units)
    events = apply_pseudo_polyphony(events, pseudo_poly, pseudo_poly_step_units)
    return merge_identical(events)


def merge_identical(events: list[list[int]]) -> list[list[int]]:
    if not events:
        return []
    merged = [events[0][:]]
    for note_value, duration_units in events[1:]:
        if merged[-1][0] == note_value:
            merged[-1][1] += duration_units
        else:
            merged.append([note_value, duration_units])
    return merged


def smooth_events(events: list[list[int]], smooth_units: int) -> list[list[int]]:
    if smooth_units <= 0 or not events:
        return events

    smoothed = [event[:] for event in events]

    while True:
        changed = False
        idx = 0

        while idx < len(smoothed):
            note_value, duration_units = smoothed[idx]
            if duration_units > smooth_units:
                idx += 1
                continue

            prev_idx = idx - 1 if idx > 0 else -1
            next_idx = idx + 1 if idx + 1 < len(smoothed) else -1
            prev_note = smoothed[prev_idx][0] if prev_idx >= 0 else 0
            next_note = smoothed[next_idx][0] if next_idx >= 0 else 0

            if note_value == 0:
                if prev_note != 0 and next_note != 0 and prev_note == next_note:
                    smoothed[prev_idx][1] += duration_units + smoothed[next_idx][1]
                    del smoothed[idx:idx + 2]
                    changed = True
                    break
                if prev_note != 0:
                    smoothed[prev_idx][1] += duration_units
                    del smoothed[idx]
                    changed = True
                    break
                if next_note != 0:
                    smoothed[next_idx][1] += duration_units
                    del smoothed[idx]
                    changed = True
                    break
            else:
                if prev_note == note_value and prev_note != 0:
                    smoothed[prev_idx][1] += duration_units
                    del smoothed[idx]
                    changed = True
                    break
                if next_note == note_value and next_note != 0:
                    smoothed[next_idx][1] += duration_units
                    del smoothed[idx]
                    changed = True
                    break
                if prev_note != 0 and next_note != 0 and prev_note == next_note:
                    smoothed[prev_idx][1] += duration_units + smoothed[next_idx][1]
                    del smoothed[idx:idx + 2]
                    changed = True
                    break
                if prev_note != 0 and next_note != 0:
                    if smoothed[prev_idx][1] >= smoothed[next_idx][1]:
                        smoothed[prev_idx][1] += duration_units
                        del smoothed[idx]
                    else:
                        smoothed[next_idx][1] += duration_units
                        del smoothed[idx]
                    changed = True
                    break

            idx += 1

        if not changed:
            return merge_identical(smoothed)


def split_long_notes(
    events: list[list[int]],
    max_note_units: int,
    retrigger_gap_units: int,
) -> list[list[int]]:
    if max_note_units <= 0:
        return events

    split: list[list[int]] = []
    for note_value, duration_units in events:
        if note_value == 0 or duration_units <= max_note_units:
            split.append([note_value, duration_units])
            continue

        remaining = duration_units
        while remaining > 0:
            if remaining <= max_note_units:
                split.append([note_value, remaining])
                break

            split.append([note_value, max_note_units])
            remaining -= max_note_units

            if retrigger_gap_units > 0 and remaining > 1:
                gap = min(retrigger_gap_units, remaining - 1)
                split.append([0, gap])
                remaining -= gap

    return split


def choose_pseudo_poly_support(note_value: int) -> int:
    for delta in (12, 7, 5, 4):
        support_note = note_value - delta
        if support_note >= X07_NOTE_MIN:
            return support_note
    return note_value


def apply_pseudo_polyphony(
    events: list[list[int]],
    pseudo_poly: int,
    pseudo_poly_step_units: int,
) -> list[list[int]]:
    if pseudo_poly != 2 or pseudo_poly_step_units <= 0:
        return events

    layered: list[list[int]] = []

    for note_value, duration_units in events:
        if note_value == 0 or duration_units <= pseudo_poly_step_units:
            layered.append([note_value, duration_units])
            continue

        support_note = choose_pseudo_poly_support(note_value)
        if support_note == note_value:
            layered.append([note_value, duration_units])
            continue

        remaining = duration_units
        play_support = False
        while remaining > 0:
            chunk = min(pseudo_poly_step_units, remaining)
            layered.append([support_note if play_support else note_value, chunk])
            remaining -= chunk
            play_support = not play_support

    return layered


def map_bass_note_to_x07(note: int, transpose: int, fold_octaves: bool) -> int | None:
    mapped = midi_to_x07(note, transpose, fold_octaves)
    if mapped is None:
        return None
    while mapped - 12 >= X07_NOTE_MIN:
        mapped -= 12
    return mapped


def map_drum_note_to_x07(note: int) -> tuple[int, int] | None:
    if note in (35, 36):      # kick
        return 1, 2
    if note in (37, 38, 39, 40):  # snare / clap
        return 4, 1
    if note in (41, 43, 45, 47, 48, 50):  # toms
        return 3, 1
    if note in (42, 44, 46, 49, 51, 52, 53, 55, 57, 59):  # hats / cymbals / ride
        return 6, 1
    return None


def build_bass_pulses(
    notes: list[MidiNote],
    ticks_per_beat: int,
    tempo_points: list[TempoPoint],
    tempo_ticks: list[int],
    unit_ms: int,
    transpose: int,
    fold_octaves: bool,
    bass_pulse_units: int,
) -> list[tuple[int, int, int]]:
    if bass_pulse_units <= 0:
        return []

    unit_us = unit_ms * 1000
    lowest_by_start: dict[int, int] = {}

    for note in notes:
        if note.note > 60:
            continue
        start_us = tick_to_us(note.start_tick, tempo_points, tempo_ticks, ticks_per_beat)
        start_unit = max(0, int(round(start_us / unit_us)))
        current = lowest_by_start.get(start_unit)
        if current is None or note.note < current:
            lowest_by_start[start_unit] = note.note

    pulses: list[tuple[int, int, int]] = []
    last_start = -9999
    for start_unit in sorted(lowest_by_start):
        if start_unit - last_start < bass_pulse_units:
            continue
        mapped = map_bass_note_to_x07(lowest_by_start[start_unit], transpose, fold_octaves)
        if mapped is None:
            continue
        pulses.append((start_unit, bass_pulse_units, mapped))
        last_start = start_unit

    return pulses


def build_drum_pulses(
    notes: list[MidiNote],
    ticks_per_beat: int,
    tempo_points: list[TempoPoint],
    tempo_ticks: list[int],
    unit_ms: int,
    drum_pulse_units: int,
) -> list[tuple[int, int, int]]:
    if drum_pulse_units <= 0:
        return []

    unit_us = unit_ms * 1000
    pulses_by_start: dict[int, tuple[int, int]] = {}

    for note in notes:
        mapped = map_drum_note_to_x07(note.note)
        if mapped is None:
            continue
        mapped_note, default_units = mapped
        start_us = tick_to_us(note.start_tick, tempo_points, tempo_ticks, ticks_per_beat)
        start_unit = max(0, int(round(start_us / unit_us)))
        pulses_by_start[start_unit] = (mapped_note, max(drum_pulse_units, default_units))

    return [
        (start_unit, duration_units, mapped_note)
        for start_unit, (mapped_note, duration_units) in sorted(pulses_by_start.items())
    ]


def events_to_unit_array(events: list[list[int]]) -> list[int]:
    units: list[int] = []
    for note_value, duration_units in events:
        units.extend([note_value] * duration_units)
    return units


def unit_array_to_events(units: list[int]) -> list[list[int]]:
    if not units:
        return []

    events: list[list[int]] = []
    current_note = units[0]
    current_duration = 1

    for note_value in units[1:]:
        if note_value == current_note:
            current_duration += 1
        else:
            events.append([current_note, current_duration])
            current_note = note_value
            current_duration = 1

    events.append([current_note, current_duration])
    return events


def overlay_pulses(events: list[list[int]], pulses: list[tuple[int, int, int]]) -> list[list[int]]:
    if not events or not pulses:
        return events

    units = events_to_unit_array(events)
    total_units = len(units)

    for start_unit, duration_units, note_value in pulses:
        if start_unit >= total_units or duration_units <= 0:
            continue
        end_unit = min(total_units, start_unit + duration_units)
        for idx in range(start_unit, end_unit):
            units[idx] = note_value

    return unit_array_to_events(units)


def overlay_pulses_staccato(
    events: list[list[int]],
    pulses: list[tuple[int, int, int]],
    gap_units: int,
) -> list[list[int]]:
    if gap_units <= 0:
        return overlay_pulses(events, pulses)
    if not events or not pulses:
        return events

    units = events_to_unit_array(events)
    total_units = len(units)
    pulse_starts = {start_unit for start_unit, _, _ in pulses if 0 <= start_unit < total_units}

    for start_unit, duration_units, note_value in pulses:
        if start_unit >= total_units or duration_units <= 0:
            continue

        end_unit = min(total_units, start_unit + duration_units)
        for idx in range(start_unit, end_unit):
            units[idx] = note_value

        gap_end = min(total_units, end_unit + gap_units)
        for idx in range(end_unit, gap_end):
            if idx in pulse_starts:
                break
            units[idx] = 0

    return unit_array_to_events(units)


def encode_pair8(events: list[list[int]]) -> bytes:
    out = bytearray()
    for note_value, duration_units in events:
        remaining = duration_units
        while remaining > 255:
            out.extend((note_value, 255))
            remaining -= 255
        out.extend((note_value, remaining))
    out.append(0xFF)
    return bytes(out)


def encode_packed4(events: list[list[int]]) -> bytes:
    out = bytearray()
    short_map = {duration: idx for idx, duration in enumerate(SHORT_DURATIONS)}

    for note_value, duration_units in events:
        remaining = duration_units
        while remaining > 0:
            if remaining in short_map:
                out.append(short_map[remaining] * 49 + note_value)
                remaining = 0
            elif remaining <= 255:
                out.extend((0xFC, note_value, remaining))
                remaining = 0
            elif remaining <= 65535:
                out.extend((0xFD, note_value, remaining & 0xFF, (remaining >> 8) & 0xFF))
                remaining = 0
            else:
                out.extend((0xFD, note_value, 0xFF, 0xFF))
                remaining -= 65535

    out.append(0xFF)
    return bytes(out)


def format_db_lines(payload: bytes) -> list[str]:
    lines = []
    for idx in range(0, len(payload), 12):
        chunk = payload[idx:idx + 12]
        lines.append("\t.db " + ",".join(f"${byte:02X}" for byte in chunk))
    return lines


def sanitize_display_name(path: str, max_length: int) -> str:
    basename = os.path.basename(path)
    cleaned = []
    for ch in basename:
        if 32 <= ord(ch) <= 126 and ch != '"':
            cleaned.append(ch)
        else:
            cleaned.append("_")
    display_name = "".join(cleaned)
    if len(display_name) <= max_length:
        return display_name

    stem, suffix = os.path.splitext(display_name)
    if suffix and len(suffix) < max_length:
        stem_len = max_length - len(suffix)
        return stem[:stem_len] + suffix
    return display_name[:max_length]


def unit_ms_to_beep_ticks(unit_ms: int) -> int:
    return max(1, (unit_ms + 25) // 50)


def build_metadata_lines(
    selected_format: str,
    unit_ms: int,
    display_name: str,
    source_size: int,
    text_size: int,
    payload_size: int,
    size_text: str,
) -> list[str]:
    format_symbol = "MUSIC_FORMAT_PACKED4" if selected_format == "packed4" else "MUSIC_FORMAT_PAIR8"
    return [
        "MUSIC_FORMAT_PAIR8\tequ 0",
        "MUSIC_FORMAT_PACKED4\tequ 1",
        f"MUSIC_DATA_FORMAT\tequ {format_symbol}",
        f"MUSIC_DATA_UNIT_MS\tequ {unit_ms}",
        f"MUSIC_DATA_BEEP_TICKS\tequ {unit_ms_to_beep_ticks(unit_ms)}",
        f"MUSIC_DATA_SOURCE_BYTES\tequ {source_size}",
        f"MUSIC_DATA_TEXT_BYTES\tequ {text_size}",
        f"MUSIC_DATA_PAYLOAD_BYTES\tequ {payload_size}",
        f"MUSIC_DATA_NAME_LEN\tequ {len(display_name)}",
        f'music_data_name:\t.db "{display_name}",0',
        f"MUSIC_DATA_SIZE_TEXT_LEN\tequ {len(size_text)}",
        f'music_data_size_text:\t.db "{size_text}",0',
    ]


def build_report(
    source_name: str,
    source_size: int,
    track_names: list[str],
    kept_notes: int,
    events: list[list[int]],
    transpose: int,
    max_x07_note: int,
    smooth_units: int,
    pseudo_poly: int,
    pseudo_poly_step_units: int,
    x07_groove: bool,
    bass_pulse_units: int,
    bass_gap_units: int,
    drum_pulse_units: int,
    selected_format: str,
    pair_bytes: bytes,
    packed_bytes: bytes,
    unit_ms: int,
) -> list[str]:
    lines = [
        f"; generated from {source_name}",
        f"; source_bytes={source_size}",
        f"; tracks: {len(track_names)} | notes kept: {kept_notes} | events: {len(events)}",
        f"; unit_ms={unit_ms} | beep_ticks={unit_ms_to_beep_ticks(unit_ms)} | transpose={transpose:+d} | max_x07_note={max_x07_note} | smooth_units={smooth_units} | pseudo_poly={pseudo_poly} | pseudo_poly_step_units={pseudo_poly_step_units} | x07_groove={int(x07_groove)} | bass_pulse_units={bass_pulse_units} | bass_gap_units={bass_gap_units} | drum_pulse_units={drum_pulse_units} | pair8={len(pair_bytes)} bytes | packed4={len(packed_bytes)} bytes",
        f"; selected format: {selected_format}",
        "; packed4: short=durations 1/2/4/8, $FC note dur8, $FD note dur16lo dur16hi, $FF end",
        "; pair8: note,duration pairs, $FF end",
        "; sample player reads MUSIC_DATA_FORMAT and MUSIC_DATA_BEEP_TICKS from this file",
    ]
    return lines


def print_track_list(notes: list[MidiNote], track_names: list[str]) -> None:
    by_track: dict[int, list[MidiNote]] = {}
    for note in notes:
        by_track.setdefault(note.track, []).append(note)

    for track_index, track_name in enumerate(track_names):
        track_notes = by_track.get(track_index, [])
        if not track_notes:
            print(f"{track_index}: {track_name} | notes=0")
            continue

        channels = ",".join(str(channel + 1) for channel in sorted({note.channel for note in track_notes}))
        note_min = min(note.note for note in track_notes)
        note_max = max(note.note for note in track_notes)
        print(
            f"{track_index}: {track_name} | notes={len(track_notes)} | channels={channels} | range={note_min}..{note_max}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a MIDI file into compact monophonic music data for the Canon X-07."
    )
    parser.add_argument("input_midi", help="Path to the source MIDI file.")
    parser.add_argument("-o", "--output", help="Output .inc/.asm file (default: music_data.inc).")
    parser.add_argument("--bin-output", help="Optional raw binary output file.")
    parser.add_argument("--list-tracks", action="store_true",
                        help="List MIDI tracks with note counts, channels and note ranges, then exit.")
    parser.add_argument("--format", choices=("auto", "pair8", "packed4"), default="auto",
                        help="Output format. auto selects the smallest one.")
    parser.add_argument("--unit-ms", type=int, default=100,
                        help="Time quantization in milliseconds. Larger values produce simpler and smaller music.")
    parser.add_argument("--min-note-units", type=int, default=1,
                        help="Drop notes shorter than this many time units.")
    parser.add_argument("--min-rest-units", type=int, default=1,
                        help="Drop rests shorter than this many time units.")
    parser.add_argument("--merge-gap-units", type=int, default=1,
                        help="Merge NOTE + short rest + same NOTE when the rest is no longer than this value.")
    parser.add_argument("--smooth-units", type=int, default=0,
                        help="Smooth very short rests and notes up to this duration.")
    parser.add_argument("--max-note-units", type=int, default=0,
                        help="Split long notes into shorter segments. 0 disables the feature.")
    parser.add_argument("--retrigger-gap-units", type=int, default=0,
                        help="Insert a small rest between split note segments.")
    parser.add_argument("--pseudo-poly", type=int, choices=(0, 2), default=0,
                        help="Fake 2 voices by rapidly alternating the melody and a lower support note.")
    parser.add_argument("--pseudo-poly-step-units", type=int, default=2,
                        help="Duration of each alternation step in pseudo-poly mode.")
    parser.add_argument("--x07-groove", action="store_true",
                        help="Add short low bass and drum pulses that usually sound better on the X-07 buzzer.")
    parser.add_argument("--bass-pulse-units", type=int, default=2,
                        help="Duration of bass pulses added by --x07-groove.")
    parser.add_argument("--bass-gap-units", type=int, default=1,
                        help="Small rest inserted after each bass pulse to keep the rhythm audible.")
    parser.add_argument("--drum-pulse-units", type=int, default=1,
                        help="Duration of drum pulses added by --x07-groove.")
    parser.add_argument("--track", type=int, action="append",
                        help="Keep only this MIDI track (0-based index). Repeatable.")
    parser.add_argument("--prefer-track", type=int, action="append",
                        help="Prefer this MIDI track when several notes overlap. Repeatable.")
    parser.add_argument("--exclude-track", type=int, action="append",
                        help="Exclude this MIDI track (0-based index). Repeatable.")
    parser.add_argument("--channel", type=int, action="append",
                        help="Keep only this MIDI channel (1..16). Repeatable.")
    parser.add_argument("--exclude-channel", type=int, action="append",
                        help="Exclude this MIDI channel (1..16). Repeatable.")
    parser.add_argument("--include-drums", action="store_true",
                        help="Include channel 10 drums. With --x07-groove, drum events are converted to simplified pulses.")
    parser.add_argument("--priority", choices=("highest", "newest", "melody"), default="highest",
                        help="Monophonic reduction strategy.")
    parser.add_argument("--transpose", type=int,
                        help="Transpose in semitones. By default the script chooses an automatic octave offset.")
    parser.add_argument("--no-fold-octaves", action="store_true",
                        help="Do not fold out-of-range notes back by octaves.")
    parser.add_argument("--max-x07-note", type=int, default=X07_NOTE_MAX,
                        help="Fold notes above this X-07 pitch down by one or more octaves (1..48).")
    args = parser.parse_args()

    if args.unit_ms <= 0:
        print("Error: --unit-ms must be > 0.", file=sys.stderr)
        return 1
    if (
        args.smooth_units < 0
        or args.max_note_units < 0
        or args.retrigger_gap_units < 0
        or args.bass_pulse_units < 0
        or args.bass_gap_units < 0
        or args.drum_pulse_units < 0
        or args.pseudo_poly_step_units <= 0
    ):
        print("Error: --smooth-units, --max-note-units, --retrigger-gap-units, --bass-pulse-units, --bass-gap-units and --drum-pulse-units must be >= 0, and --pseudo-poly-step-units must be > 0.", file=sys.stderr)
        return 1
    if not X07_NOTE_MIN <= args.max_x07_note <= X07_NOTE_MAX:
        print(f"Error: --max-x07-note must be between {X07_NOTE_MIN} and {X07_NOTE_MAX}.", file=sys.stderr)
        return 1

    try:
        ticks_per_beat, notes, tempo_events, track_names = parse_midi(args.input_midi)
    except ValueError as exc:
        print(f"MIDI error: {exc}", file=sys.stderr)
        return 1

    if args.list_tracks:
        print_track_list(notes, track_names)
        return 0

    if args.track:
        track_filter = set(args.track)
        notes = [note for note in notes if note.track in track_filter]
    if args.exclude_track:
        excluded_tracks = set(args.exclude_track)
        notes = [note for note in notes if note.track not in excluded_tracks]

    if args.channel:
        channel_filter = {channel - 1 for channel in args.channel}
        notes = [note for note in notes if note.channel in channel_filter]
    if args.exclude_channel:
        excluded_channels = {channel - 1 for channel in args.exclude_channel}
        notes = [note for note in notes if note.channel not in excluded_channels]

    drum_notes = [note for note in notes if note.channel == 9]
    music_notes = [note for note in notes if note.channel != 9]

    if args.x07_groove:
        notes_for_mono = music_notes
    elif args.include_drums:
        notes_for_mono = notes
    else:
        notes_for_mono = music_notes

    if not notes_for_mono:
        print("No usable notes left after filtering.", file=sys.stderr)
        return 1

    try:
        source_size = os.path.getsize(args.input_midi)
    except OSError as exc:
        print(f"File size error: {exc}", file=sys.stderr)
        return 1

    tempo_points, tempo_ticks = build_tempo_map(ticks_per_beat, tempo_events)
    preferred_tracks = set(args.prefer_track or [])
    spans = reduce_to_mono(
        notes_for_mono,
        ticks_per_beat,
        tempo_points,
        tempo_ticks,
        args.priority,
        preferred_tracks=preferred_tracks,
    )

    if args.transpose is None:
        transpose = choose_auto_transpose([note.note for note in notes_for_mono])
    else:
        transpose = args.transpose

    events = simplify_events(
        spans=spans,
        unit_ms=args.unit_ms,
        min_note_units=args.min_note_units,
        min_rest_units=args.min_rest_units,
        merge_gap_units=args.merge_gap_units,
        smooth_units=args.smooth_units,
        transpose=transpose,
        fold_octaves=not args.no_fold_octaves,
        max_x07_note=args.max_x07_note,
        max_note_units=args.max_note_units,
        retrigger_gap_units=args.retrigger_gap_units,
        pseudo_poly=args.pseudo_poly,
        pseudo_poly_step_units=args.pseudo_poly_step_units,
    )

    if not events:
        print("Simplification removed all musical events.", file=sys.stderr)
        return 1

    if args.x07_groove:
        bass_pulses = build_bass_pulses(
            notes=music_notes,
            ticks_per_beat=ticks_per_beat,
            tempo_points=tempo_points,
            tempo_ticks=tempo_ticks,
            unit_ms=args.unit_ms,
            transpose=transpose,
            fold_octaves=not args.no_fold_octaves,
            bass_pulse_units=args.bass_pulse_units,
        )
        if bass_pulses:
            events = overlay_pulses_staccato(events, bass_pulses, args.bass_gap_units)

        if args.include_drums and drum_notes:
            drum_pulses = build_drum_pulses(
                notes=drum_notes,
                ticks_per_beat=ticks_per_beat,
                tempo_points=tempo_points,
                tempo_ticks=tempo_ticks,
                unit_ms=args.unit_ms,
                drum_pulse_units=args.drum_pulse_units,
            )
            if drum_pulses:
                events = overlay_pulses(events, drum_pulses)

        events = merge_identical(events)

    pair_bytes = encode_pair8(events)
    packed_bytes = encode_packed4(events)

    if args.format == "auto":
        if len(packed_bytes) <= len(pair_bytes):
            selected_format = "packed4"
            payload = packed_bytes
        else:
            selected_format = "pair8"
            payload = pair_bytes
    elif args.format == "pair8":
        selected_format = "pair8"
        payload = pair_bytes
    else:
        selected_format = "packed4"
        payload = packed_bytes

    label = "music_data"
    output_path = args.output or "music_data.inc"

    header_lines = build_report(
        source_name=os.path.basename(args.input_midi),
        source_size=source_size,
        track_names=track_names,
        kept_notes=len(notes_for_mono),
        events=events,
        transpose=transpose,
        max_x07_note=args.max_x07_note,
        smooth_units=args.smooth_units,
        pseudo_poly=args.pseudo_poly,
        pseudo_poly_step_units=args.pseudo_poly_step_units,
        x07_groove=args.x07_groove,
        bass_pulse_units=args.bass_pulse_units,
        bass_gap_units=args.bass_gap_units,
        drum_pulse_units=args.drum_pulse_units,
        selected_format=selected_format,
        pair_bytes=pair_bytes,
        packed_bytes=packed_bytes,
        unit_ms=args.unit_ms,
    )
    body_lines = [f"{label}:"] + format_db_lines(payload)
    payload_size = len(payload)
    text_size = 0
    size_text = f"{payload_size} bytes"
    asm_text = ""

    for _ in range(8):
        max_display_name_len = min(30, max(1, 40 - len(size_text)))
        display_name = sanitize_display_name(args.input_midi, max_display_name_len)
        metadata_lines = build_metadata_lines(
            selected_format,
            args.unit_ms,
            display_name,
            source_size,
            text_size,
            payload_size,
            size_text,
        )
        asm_lines = header_lines + metadata_lines + body_lines
        asm_text = "\n".join(asm_lines) + "\n"
        new_text_size = len(asm_text.encode("utf-8"))
        if new_text_size == text_size:
            text_size = new_text_size
            break
        text_size = new_text_size

    max_display_name_len = min(30, max(1, 40 - len(size_text)))
    display_name = sanitize_display_name(args.input_midi, max_display_name_len)
    metadata_lines = build_metadata_lines(
        selected_format,
        args.unit_ms,
        display_name,
        source_size,
        text_size,
        payload_size,
        size_text,
    )
    asm_lines = header_lines + metadata_lines + body_lines
    asm_text = "\n".join(asm_lines) + "\n"

    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(asm_text)

    if args.bin_output:
        with open(args.bin_output, "wb") as handle:
            handle.write(payload)

    print(f"OK: {len(events)} events, format {selected_format}, {len(payload)} bytes.")
    print(f"ASM output: {output_path}")
    if args.bin_output:
        print(f"Binary output: {args.bin_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
