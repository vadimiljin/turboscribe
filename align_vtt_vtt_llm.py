#!/usr/bin/env python3
"""
VTT-to-VTT alignment with LLM enhancement for ambiguous cases.

Strategy:
1. Time-based matching (strict, no text similarity from broken zoom.vtt)
2. High confidence cases → direct assignment
3. Ambiguous cases → LLM decision with context
4. All decisions are logged with reasoning

Usage:
    python align_vtt_vtt_llm.py <folder_path> [--verbose]
    
Example:
    python align_vtt_vtt_llm.py "Product_Review_2025/46. Product Review 13 Nov"
    python align_vtt_vtt_llm.py "Product_Review_2025/46. Product Review 13 Nov" --verbose
"""

import re
import json
import os
import sys
import glob
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import Counter
from datetime import datetime
from pathlib import Path

# OpenAI import (will use if available)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[!] OpenAI not installed. Run: pip install openai")


@dataclass
class VTTSegment:
    start: float
    end: float
    speaker: str
    text: str


@dataclass
class AlignedSegment:
    start: float
    end: float
    speaker: str
    text: str
    confidence: float
    match_type: str  # "high_confidence", "llm_resolved", "fallback"
    reasoning: str = ""  # Why this speaker was chosen
    candidates: List[Dict] = None  # All candidates considered


def parse_timestamp(ts: str) -> float:
    """Parse VTT timestamp to seconds."""
    parts = ts.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def parse_vtt_with_speakers(filepath: str) -> List[VTTSegment]:
    """Parse zoom.vtt - ONLY use for timestamps and speaker names, NOT text."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    segments = []
    blocks = re.split(r'\n\n+', content)
    
    for block in blocks:
        if not block.strip() or block.strip() == 'WEBVTT':
            continue
        
        lines = block.strip().split('\n')
        timestamp_line = None
        text_lines = []
        
        for line in lines:
            if '-->' in line:
                timestamp_line = line
            elif line.strip() and not line.strip().isdigit():
                text_lines.append(line.strip())
        
        if not timestamp_line or not text_lines:
            continue
        
        match = re.search(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})', timestamp_line)
        if not match:
            continue
        
        start = parse_timestamp(match.group(1))
        end = parse_timestamp(match.group(2))
        
        # Extract speaker name ONLY (text from zoom.vtt is unreliable!)
        first_line = text_lines[0]
        speaker_match = re.match(r'^([^:]+):\s*(.*)$', first_line)
        
        if speaker_match:
            speaker = speaker_match.group(1).strip()
        else:
            speaker = "Unknown"
        
        # Store empty text - we don't use zoom.vtt text!
        segments.append(VTTSegment(start=start, end=end, speaker=speaker, text=""))
    
    return segments


def parse_turboscribe_format(filepath: str) -> List[VTTSegment]:
    """
    Parse TurboScribe format VTT file.
    Format: [Speaker X] (MM:SS - MM:SS) or (H:MM:SS - H:MM:SS)
    Text follows on same or next lines.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    segments = []
    
    # Regex to match: [Speaker X] (time - time)
    pattern = r'\[Speaker\s+(\d+)\]\s*\((\d{1,2}):(\d{2}):?(\d{2})?\s*-\s*(\d{1,2}):(\d{2}):?(\d{2})?\)'
    
    matches = list(re.finditer(pattern, content))
    
    for i, match in enumerate(matches):
        speaker_num = match.group(1)
        speaker = f"[SPEAKER_{speaker_num}]"
        
        # Parse start time
        start_h = int(match.group(2)) if match.group(4) else 0
        start_m = int(match.group(3)) if match.group(4) else int(match.group(2))
        start_s = int(match.group(4)) if match.group(4) else int(match.group(3))
        start = start_h * 3600 + start_m * 60 + start_s
        
        # Parse end time
        end_h = int(match.group(5)) if match.group(7) else 0
        end_m = int(match.group(6)) if match.group(7) else int(match.group(5))
        end_s = int(match.group(7)) if match.group(7) else int(match.group(6))
        end = end_h * 3600 + end_m * 60 + end_s
        
        # Extract text until next speaker or end
        text_start = match.end()
        if i + 1 < len(matches):
            text_end = matches[i + 1].start()
        else:
            text_end = len(content)
        
        text = content[text_start:text_end].strip()
        # Remove special markers
        text = re.sub(r'\(This file is longer than.*?\)', '', text, flags=re.DOTALL)
        text = text.strip()
        
        if text:
            segments.append(VTTSegment(start=start, end=end, speaker="", text=text))
    
    return segments


def detect_vtt_format(filepath: str) -> str:
    """Detect VTT format type."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read(1000)  # Read first 1000 chars
    
    # Check for TurboScribe format - [Speaker X] (MM:SS - MM:SS) pattern
    if '[Speaker' in content and re.search(r'\[Speaker\s+\d+\]\s*\(\d{1,2}:\d{2}', content):
        return 'turboscribe'
    
    # Standard VTT format has "WEBVTT" and "-->" timestamps
    if 'WEBVTT' in content or '-->' in content:
        return 'standard'
    
    # If file ends with .txt and has Speaker pattern, assume TurboScribe
    if filepath.endswith('.txt') and '[Speaker' in content:
        return 'turboscribe'
    
    # Default to standard
    return 'standard'


def parse_vtt_without_speakers(filepath: str) -> List[VTTSegment]:
    """Parse turboscribe.vtt - high quality text, no speakers OR numbered speakers."""
    
    # Detect format
    fmt = detect_vtt_format(filepath)
    
    if fmt == 'turboscribe':
        return parse_turboscribe_format(filepath)
    
    # Standard VTT format
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    segments = []
    blocks = re.split(r'\n\n+', content)
    
    for block in blocks:
        if not block.strip() or block.strip() == 'WEBVTT':
            continue
        
        lines = block.strip().split('\n')
        timestamp_line = None
        text_lines = []
        
        for line in lines:
            if '-->' in line:
                timestamp_line = line
            elif line.strip() and not line.strip().isdigit():
                text_lines.append(line.strip())
        
        if not timestamp_line or not text_lines:
            continue
        
        match = re.search(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})', timestamp_line)
        if not match:
            continue
        
        start = parse_timestamp(match.group(1))
        end = parse_timestamp(match.group(2))
        
        # Join all text lines
        full_text = ' '.join(text_lines).strip()
        
        # Check if text has [SPEAKER_X] format and extract it
        speaker_tag_match = re.match(r'^\[SPEAKER_\d+\]\s*(.*)$', full_text)
        if speaker_tag_match:
            # Keep the speaker tag, extract text after it
            text = speaker_tag_match.group(1).strip()
        else:
            text = full_text
        
        segments.append(VTTSegment(start=start, end=end, speaker="", text=text))
    
    return segments


def calculate_overlap(seg1_start: float, seg1_end: float, seg2_start: float, seg2_end: float) -> float:
    """Calculate overlap duration between two segments."""
    overlap_start = max(seg1_start, seg2_start)
    overlap_end = min(seg1_end, seg2_end)
    return max(0, overlap_end - overlap_start)


def find_speaker_candidates(
    text_seg: VTTSegment,
    speaker_segs: List[VTTSegment]
) -> List[Dict]:
    """
    Find all possible speaker candidates for a text segment.
    Returns list of candidates with overlap info, sorted by overlap duration.
    """
    candidates = []
    text_duration = text_seg.end - text_seg.start
    
    for spk_seg in speaker_segs:
        overlap = calculate_overlap(
            spk_seg.start, spk_seg.end,
            text_seg.start, text_seg.end
        )
        
        if overlap > 0:
            overlap_ratio = overlap / text_duration if text_duration > 0 else 0
            candidates.append({
                'speaker': spk_seg.speaker,
                'overlap_duration': overlap,
                'overlap_ratio': overlap_ratio,
                'speaker_start': spk_seg.start,
                'speaker_end': spk_seg.end
            })
    
    # Sort by overlap duration (descending)
    candidates.sort(key=lambda x: x['overlap_duration'], reverse=True)
    
    # Group by speaker (in case same speaker appears multiple times)
    speaker_totals = {}
    for c in candidates:
        spk = c['speaker']
        if spk not in speaker_totals:
            speaker_totals[spk] = {
                'speaker': spk,
                'overlap_duration': 0,
                'overlap_ratio': 0
            }
        speaker_totals[spk]['overlap_duration'] += c['overlap_duration']
    
    # Recalculate ratios
    for spk in speaker_totals:
        speaker_totals[spk]['overlap_ratio'] = speaker_totals[spk]['overlap_duration'] / text_duration
    
    # Convert back to list and sort
    aggregated = list(speaker_totals.values())
    aggregated.sort(key=lambda x: x['overlap_duration'], reverse=True)
    
    return aggregated


def ask_llm_for_speaker(
    text_seg: VTTSegment,
    candidates: List[Dict],
    context_before: List[AlignedSegment],
    context_after: List[VTTSegment],
    client: Optional[object],
    verbose: bool = False
) -> Dict:
    """
    Ask LLM to determine the speaker for an ambiguous segment.
    
    Returns:
        {
            'speaker': str,
            'confidence': float,
            'reasoning': str
        }
    """
    if not client or not OPENAI_AVAILABLE:
        # Fallback: return top candidate
        if verbose:
            print(f"\n[LLM] Fallback (no OpenAI client) - using top candidate: {candidates[0]['speaker']}")
        return {
            'speaker': candidates[0]['speaker'],
            'confidence': candidates[0]['overlap_ratio'],
            'reasoning': 'LLM not available, using top time-overlap candidate'
        }
    
    # Build context
    context_text = "Предыдущие фрагменты:\n"
    for seg in context_before[-3:]:  # Last 3
        context_text += f"- **{seg.speaker}**: {seg.text[:100]}...\n"
    
    context_text += f"\n**ТЕКУЩИЙ ФРАГМЕНТ** [{format_time(text_seg.start)} - {format_time(text_seg.end)}]:\n"
    context_text += f'"{text_seg.text}"\n\n'
    
    context_text += "Кандидаты (по времени overlap):\n"
    for i, c in enumerate(candidates[:5], 1):  # Top 5
        context_text += f"{i}. {c['speaker']}: {c['overlap_ratio']:.1%} времени\n"
    
    if context_after:
        context_text += "\nСледующие фрагменты:\n"
        for seg in context_after[:2]:  # Next 2
            context_text += f"- {seg.text[:100]}...\n"
    
    prompt = f"""Ты эксперт по анализу транскриптов встреч. Определи, кто говорит данный фрагмент.

{context_text}

ВАЖНО:
- Используй ТОЛЬКО кандидатов из списка выше
- НЕ выдумывай новых спикеров
- Учитывай контекст разговора и логику беседы
- Если несколько человек перебивают друг друга, выбери того, кто говорит ОСНОВНУЮ часть фрагмента

Ответь в формате JSON:
{{
    "speaker": "Имя спикера",
    "confidence": 0.95,
    "reasoning": "Краткое объяснение выбора"
}}"""

    if verbose:
        print(f"\n{'='*80}")
        print(f"[LLM] CALLING LLM for segment at {format_time(text_seg.start)}")
        print(f"{'='*80}")
        print(f"Text: {text_seg.text[:150]}...")
        print(f"\nCandidates:")
        for i, c in enumerate(candidates[:5], 1):
            print(f"  {i}. {c['speaker']}: {c['overlap_ratio']:.1%}")
        print(f"\n--- PROMPT START ---")
        print(prompt)
        print(f"--- PROMPT END ---\n")


    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты эксперт по анализу транскриптов встреч. Отвечай только в JSON формате."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        if verbose:
            print(f"--- LLM RESPONSE START ---")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print(f"--- LLM RESPONSE END ---")
            print(f"[LLM] Decision: {result['speaker']} (confidence: {result.get('confidence', 0):.2f})")
            print(f"[LLM] Reasoning: {result.get('reasoning', 'N/A')}")
            print(f"{'='*80}\n")
        
        # Validate speaker is in candidates
        valid_speakers = [c['speaker'] for c in candidates]
        if result['speaker'] not in valid_speakers:
            # Fallback to top candidate
            if verbose:
                print(f"[!] LLM returned invalid speaker '{result['speaker']}', fallback to {candidates[0]['speaker']}")
            return {
                'speaker': candidates[0]['speaker'],
                'confidence': 0.7,
                'reasoning': f"LLM returned invalid speaker, using top candidate"
            }
        
        return result
        
    except Exception as e:
        print(f"[!] LLM error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return {
            'speaker': candidates[0]['speaker'],
            'confidence': candidates[0]['overlap_ratio'] * 0.8,
            'reasoning': f'LLM error, fallback to top candidate'
        }


def format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def split_turboscribe_segment_by_speakers(
    text_seg: VTTSegment,
    speaker_segs: List[VTTSegment]
) -> List[VTTSegment]:
    """
    Split a TurboScribe text segment into multiple segments based on speaker changes.
    TurboScribe gives large blocks, but transcript.vtt has detailed speaker timings.
    """
    # Find all speaker segments that overlap with this text segment
    overlapping = []
    for spk_seg in speaker_segs:
        overlap = calculate_overlap(
            spk_seg.start, spk_seg.end,
            text_seg.start, text_seg.end
        )
        if overlap > 0:
            overlapping.append(spk_seg)
    
    if not overlapping:
        return [text_seg]
    
    # Sort by start time
    overlapping.sort(key=lambda x: x.start)
    
    # If only one speaker or all same speaker, return as-is
    unique_speakers = set(seg.speaker for seg in overlapping)
    if len(unique_speakers) <= 1:
        return [text_seg]
    
    # Split text by sentences
    text = text_seg.text
    sentences = re.split(r'([.!?]\s+)', text)
    
    # Reconstruct sentences with punctuation
    full_sentences = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and re.match(r'^[.!?]\s+$', sentences[i + 1]):
            full_sentences.append(sentences[i] + sentences[i + 1].strip())
            i += 2
        else:
            if sentences[i].strip():
                full_sentences.append(sentences[i])
            i += 1
    
    if len(full_sentences) <= 1:
        return [text_seg]
    
    # Calculate duration per sentence
    total_duration = text_seg.end - text_seg.start
    duration_per_sentence = total_duration / len(full_sentences)
    
    # Create segments for each sentence
    result = []
    current_time = text_seg.start
    
    for sentence in full_sentences:
        sentence_start = current_time
        sentence_end = current_time + duration_per_sentence
        
        # Find which speaker this time belongs to
        best_speaker = None
        max_overlap = 0
        for spk_seg in overlapping:
            overlap = calculate_overlap(
                spk_seg.start, spk_seg.end,
                sentence_start, sentence_end
            )
            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = spk_seg.speaker
        
        if best_speaker:
            result.append(VTTSegment(
                start=sentence_start,
                end=sentence_end,
                speaker=best_speaker,
                text=sentence.strip()
            ))
        
        current_time = sentence_end
    
    return result if result else [text_seg]


def build_speaker_mapping(speaker_vtt: List[VTTSegment]) -> Dict[str, str]:
    """
    Build mapping from time-based speaker patterns to actual names.
    Returns: dict mapping time ranges to speaker names for quick lookup.
    """
    # Sort speakers by time
    sorted_speakers = sorted(speaker_vtt, key=lambda x: x.start)
    
    # Get unique speaker names and their total speaking time
    speaker_time = {}
    for seg in sorted_speakers:
        if seg.speaker not in speaker_time:
            speaker_time[seg.speaker] = 0
        speaker_time[seg.speaker] += (seg.end - seg.start)
    
    # Sort by speaking time (most active speakers first)
    sorted_by_time = sorted(speaker_time.items(), key=lambda x: x[1], reverse=True)
    
    print(f"   [i] Обнаружено {len(sorted_by_time)} уникальных спикеров:")
    for i, (speaker, duration) in enumerate(sorted_by_time[:8], 1):
        print(f"      {i}. {speaker}: {format_time(duration)}")
    
    return {speaker: speaker for speaker in speaker_time.keys()}


def align_with_llm(
    speaker_vtt: List[VTTSegment],
    text_vtt: List[VTTSegment],
    openai_api_key: Optional[str] = None,
    verbose: bool = False
) -> List[AlignedSegment]:
    """
    Align speaker VTT with text VTT, using LLM for ambiguous cases.
    
    Note: TurboScribe может указывать до 8 спикеров независимо от реального количества.
    Мы используем временной overlap для маппинга на реальных участников.
    """
    # Initialize OpenAI client
    client = None
    if openai_api_key and OPENAI_AVAILABLE:
        client = OpenAI(api_key=openai_api_key)
        print("[OK] OpenAI client initialized")
    else:
        print("[!] OpenAI not available, will use fallback for ambiguous cases")
    
    # Build speaker mapping
    speaker_mapping = build_speaker_mapping(speaker_vtt)
    
    aligned = []
    stats = {
        'high_confidence': 0,
        'llm_resolved': 0,
        'fallback': 0
    }
    
    # Split text segments if they span multiple speakers
    expanded_text_vtt = []
    for text_seg in text_vtt:
        split_segments = split_turboscribe_segment_by_speakers(text_seg, speaker_vtt)
        expanded_text_vtt.extend(split_segments)
    
    print(f"   [+] Расширено до {len(expanded_text_vtt)} сегментов после разделения по спикерам")
    
    llm_call_count = 0
    
    for i, text_seg in enumerate(expanded_text_vtt):
        # Progress indicator
        if not verbose and i > 0 and i % 50 == 0:
            print(f"   [PROGRESS] Обработано {i}/{len(expanded_text_vtt)} сегментов (LLM вызовов: {llm_call_count})")
        
        # If text segment already has speaker assigned, use it directly
        if text_seg.speaker:
            aligned.append(AlignedSegment(
                start=text_seg.start,
                end=text_seg.end,
                speaker=text_seg.speaker,
                text=text_seg.text,
                confidence=0.95,
                match_type="high_confidence",
                reasoning="Pre-assigned speaker from split",
                candidates=[]
            ))
            stats['high_confidence'] += 1
            continue
        
        # Find all candidates
        candidates = find_speaker_candidates(text_seg, speaker_vtt)
        
        if not candidates:
            # No overlap - find nearest
            nearest = min(speaker_vtt, key=lambda s: min(
                abs(s.start - text_seg.start),
                abs(s.end - text_seg.end)
            ))
            aligned.append(AlignedSegment(
                start=text_seg.start,
                end=text_seg.end,
                speaker=nearest.speaker,
                text=text_seg.text,
                confidence=0.3,
                match_type="fallback",
                reasoning="No time overlap, using nearest speaker",
                candidates=[]
            ))
            stats['fallback'] += 1
            continue
        
        # Classify confidence
        top_candidate = candidates[0]
        
        if len(candidates) == 1 and top_candidate['overlap_ratio'] > 0.8:
            # High confidence: single speaker, strong overlap
            aligned.append(AlignedSegment(
                start=text_seg.start,
                end=text_seg.end,
                speaker=top_candidate['speaker'],
                text=text_seg.text,
                confidence=min(0.99, top_candidate['overlap_ratio'] * 1.1),
                match_type="high_confidence",
                reasoning=f"Single speaker with {top_candidate['overlap_ratio']:.1%} overlap",
                candidates=candidates
            ))
            stats['high_confidence'] += 1
            
        elif len(candidates) > 1 and candidates[1]['overlap_ratio'] > 0.15:
            # Ambiguous: multiple speakers with significant overlap
            # Use LLM
            if not verbose:
                print(f"   [LLM] Segment #{i+1} at {format_time(text_seg.start)} - ambiguous case, calling LLM...")
            
            llm_call_count += 1
            
            context_before = aligned[-5:] if aligned else []
            context_after = text_vtt[i+1:i+3] if i+1 < len(text_vtt) else []
            
            llm_result = ask_llm_for_speaker(
                text_seg, candidates, context_before, context_after, client, verbose
            )
            
            aligned.append(AlignedSegment(
                start=text_seg.start,
                end=text_seg.end,
                speaker=llm_result['speaker'],
                text=text_seg.text,
                confidence=llm_result['confidence'],
                match_type="llm_resolved",
                reasoning=llm_result['reasoning'],
                candidates=candidates
            ))
            stats['llm_resolved'] += 1
            
        else:
            # Medium confidence: use top candidate
            aligned.append(AlignedSegment(
                start=text_seg.start,
                end=text_seg.end,
                speaker=top_candidate['speaker'],
                text=text_seg.text,
                confidence=top_candidate['overlap_ratio'],
                match_type="high_confidence",
                reasoning=f"Dominant speaker with {top_candidate['overlap_ratio']:.1%} overlap",
                candidates=candidates
            ))
            stats['high_confidence'] += 1
    
    if not aligned:
        print(f"\n[!] Не удалось создать ни одного выровненного сегмента!")
        print(f"   Проверьте, что файл с текстом содержит данные")
        return []
    
    print(f"\n[STATS] Статистика решений:")
    print(f"   High confidence (time-based): {stats['high_confidence']} ({stats['high_confidence']/len(aligned)*100:.1f}%)")
    print(f"   LLM resolved: {stats['llm_resolved']} ({stats['llm_resolved']/len(aligned)*100:.1f}%)")
    print(f"   Fallback: {stats['fallback']} ({stats['fallback']/len(aligned)*100:.1f}%)")
    print(f"   Total LLM API calls: {llm_call_count}")
    
    return aligned


def find_vtt_files(folder_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Find the speaker VTT and text VTT files in the folder.
    
    Returns:
        (speaker_vtt_path, text_vtt_path)
        speaker_vtt = file ending with .transcript.vtt (bad text, real names)
        text_vtt = file ending with .mp4.vtt OR " Recording.txt" (good text, numbered speakers)
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"[X] Папка не найдена: {folder_path}")
        return None, None
    
    # Find .transcript.vtt file (speaker names, bad text)
    # Support both "*.transcript.vtt" and "*-transcript.vtt" patterns
    transcript_files = list(folder.glob("*.transcript.vtt")) + list(folder.glob("*-transcript.vtt"))
    
    # Find good text file (numbered speakers, good text)
    # Support: *.mp4.vtt, *-mp4.vtt, OR "* Recording.txt"
    mp4_vtt_files = (
        list(folder.glob("*.mp4.vtt")) + 
        list(folder.glob("*-mp4.vtt")) +
        list(folder.glob("* Recording.txt"))
    )
    
    if not transcript_files:
        print(f"[X] Не найден файл *.transcript.vtt в папке: {folder_path}")
        return None, None
    
    if not mp4_vtt_files:
        print(f"[X] Не найден файл *.mp4.vtt или * Recording.txt в папке: {folder_path}")
        return None, None
    
    speaker_vtt = str(transcript_files[0])
    text_vtt = str(mp4_vtt_files[0])
    
    if len(transcript_files) > 1:
        print(f"[!] Найдено несколько .transcript.vtt файлов, использую: {speaker_vtt}")
    
    if len(mp4_vtt_files) > 1:
        print(f"[!] Найдено несколько файлов с текстом, использую: {text_vtt}")
    
    return speaker_vtt, text_vtt


def generate_markdown(segments: List[AlignedSegment], output_path: str):
    """Generate transcript markdown with grouped phrases."""
    lines = []
    lines.append("# Транскрипт встречи (Summary)")
    lines.append("")
    lines.append(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    if segments:
        total_duration = segments[-1].end - segments[0].start
        lines.append(f"**Длительность:** {format_time(total_duration)}")
        
        speakers = set(seg.speaker for seg in segments)
        lines.append(f"**Участники:** {len(speakers)}")
        
        avg_conf = sum(s.confidence for s in segments) / len(segments)
        lines.append(f"**Точность:** {avg_conf:.1%}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Group consecutive segments by speaker
    grouped = []
    current_group = None
    
    for seg in segments:
        if current_group is None or current_group['speaker'] != seg.speaker:
            if current_group:
                grouped.append(current_group)
            current_group = {
                'speaker': seg.speaker,
                'start': seg.start,
                'end': seg.end,
                'texts': [seg.text],
                'min_confidence': seg.confidence
            }
        else:
            current_group['end'] = seg.end
            current_group['texts'].append(seg.text)
            current_group['min_confidence'] = min(current_group['min_confidence'], seg.confidence)
    
    if current_group:
        grouped.append(current_group)
    
    # Output grouped segments
    for group in grouped:
        # Склеить все тексты одного спикера естественно
        texts = []
        for text in group['texts']:
            text = text.strip()
            # Убираем лишние точки и запятые в конце
            text = text.rstrip('.,;')
            if text:
                texts.append(text)
        
        if not texts:
            continue
        
        # Соединяем через ". " для разделения предложений
        combined_text = '. '.join(texts) + '.'
        
        start_time = format_time(group['start'])
        end_time = format_time(group['end'])
        
        lines.append(f"**{group['speaker']}** [{start_time} - {end_time}]: {combined_text}")
        lines.append("")
    
    # Statistics
    lines.append("---")
    lines.append("")
    lines.append("## Статистика")
    lines.append("")
    
    speaker_counts = Counter(seg.speaker for seg in segments)
    lines.append("### Участники")
    lines.append("")
    
    total_duration = segments[-1].end - segments[0].start
    for speaker, count in speaker_counts.most_common():
        speaker_segs = [s for s in segments if s.speaker == speaker]
        speaker_duration = sum(s.end - s.start for s in speaker_segs)
        speaker_conf = sum(s.confidence for s in speaker_segs) / len(speaker_segs)
        
        lines.append(f"- **{speaker}**: {count} сегментов, {format_time(speaker_duration)} ({speaker_duration/total_duration*100:.1f}%), точность {speaker_conf:.1%}")
    
    lines.append("")
    lines.append("### Качество выравнивания")
    lines.append("")
    
    match_types = Counter(seg.match_type for seg in segments)
    lines.append(f"- Высокая уверенность (time-based): {match_types['high_confidence']} ({match_types['high_confidence']/len(segments)*100:.1f}%)")
    lines.append(f"- Разрешено через LLM: {match_types['llm_resolved']} ({match_types['llm_resolved']/len(segments)*100:.1f}%)")
    lines.append(f"- Fallback: {match_types.get('fallback', 0)} ({match_types.get('fallback', 0)/len(segments)*100:.1f}%)")
    
    avg_conf = sum(s.confidence for s in segments) / len(segments)
    lines.append(f"- Средняя уверенность: {avg_conf:.1%}")
    
    low_conf = [s for s in segments if s.confidence < 0.7]
    if low_conf:
        lines.append(f"- [!] Низкая уверенность (<70%): {len(low_conf)} сегментов ({len(low_conf)/len(segments)*100:.1f}%)")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def generate_jsonl(segments: List[AlignedSegment], output_path: str):
    """Generate clean JSONL for production use."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            data = {
                'start': round(seg.start, 2),
                'end': round(seg.end, 2),
                'speaker': seg.speaker,
                'text': seg.text,
                'confidence': round(seg.confidence, 2)
            }
            f.write(json.dumps(data, ensure_ascii=False) + '\n')


def generate_vtt(segments: List[AlignedSegment], output_path: str):
    """Generate VTT output file."""
    lines = ["WEBVTT", ""]
    
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        
        # Format timestamps
        start_h = int(seg.start // 3600)
        start_m = int((seg.start % 3600) // 60)
        start_s = seg.start % 60
        
        end_h = int(seg.end // 3600)
        end_m = int((seg.end % 3600) // 60)
        end_s = seg.end % 60
        
        start_ts = f"{start_h:02d}:{start_m:02d}:{start_s:06.3f}"
        end_ts = f"{end_h:02d}:{end_m:02d}:{end_s:06.3f}"
        
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(f"{seg.speaker}: {seg.text}")
        lines.append("")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    print("=" * 80)
    print("VTT-TO-VTT ВЫРАВНИВАНИЕ С LLM")
    print("=" * 80)
    print()
    
    # Check arguments
    if len(sys.argv) < 2:
        print("[X] Использование: python align_vtt_vtt_llm.py <folder_path> [--verbose]")
        print()
        print("Пример:")
        print('  python align_vtt_vtt_llm.py "Product_Review_2025/46. Product Review 13 Nov"')
        print('  python align_vtt_vtt_llm.py "Product_Review_2025/46. Product Review 13 Nov" --verbose')
        print()
        print("Скрипт автоматически найдет:")
        print("  - *.transcript.vtt (имена спикеров, плохой текст)")
        print("  - *.mp4.vtt или * Recording.txt (номера спикеров, хороший текст)")
        print()
        print("Опции:")
        print("  --verbose  Показывать детали LLM запросов и ответов")
        print()
        sys.exit(1)
    
    folder_path = sys.argv[1]
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    
    if verbose:
        print("[MODE] Verbose mode ENABLED - будут показаны все LLM запросы и ответы")
        print()
    folder = Path(folder_path)
    
    # Get folder name for output files (replace spaces with underscores)
    folder_name = folder.name.replace(' ', '_')
    
    print(f"[DIR] Папка: {folder_path}")
    print(f"[FILE] Базовое имя: {folder_name}")
    print()
    
    # Find VTT files
    print("[SEARCH] Поиск VTT файлов...")
    speaker_vtt_path, text_vtt_path = find_vtt_files(folder_path)
    
    if not speaker_vtt_path or not text_vtt_path:
        sys.exit(1)
    
    print(f"   [+] Спикеры: {Path(speaker_vtt_path).name}")
    print(f"   [+] Текст: {Path(text_vtt_path).name}")
    
    # Output paths
    output_vtt_path = str(folder / f"{folder_name}-transcript.vtt")
    output_md_path = str(folder / f"{folder_name}-transcript.md")
    output_jsonl_path = str(folder / f"{folder_name}-transcript.jsonl")
    
    # Get API key from environment or prompt
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("\n[!] OPENAI_API_KEY not found in environment")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        print("Or the script will use fallback for ambiguous cases")
        print()
    
    # Parse
    print("[READ] Чтение VTT с именами спикеров (*.transcript.vtt)...")
    speaker_vtt = parse_vtt_with_speakers(speaker_vtt_path)
    print(f"   [+] {len(speaker_vtt)} сегментов")
    print(f"   [+] {len(set(s.speaker for s in speaker_vtt))} уникальных спикеров")
    
    print("\n[READ] Чтение файла с качественным текстом...")
    print("   [i] TurboScribe: до 8 спикеров (независимо от реального количества)")
    text_vtt = parse_vtt_without_speakers(text_vtt_path)
    print(f"   [+] {len(text_vtt)} сегментов")
    
    # Align
    print("\n[PROC] Выравнивание с LLM enhancement...")
    aligned = align_with_llm(speaker_vtt, text_vtt, api_key, verbose)
    
    if not aligned:
        print("\n[X] Выравнивание не удалось - нет сегментов для обработки")
        sys.exit(1)
    
    print(f"   [+] {len(aligned)} выровненных сегментов")
    
    # Generate outputs
    print("\n[FILE] Генерация выходных файлов...")
    generate_vtt(aligned, output_vtt_path)
    print(f"   [+] Transcript VTT: {Path(output_vtt_path).name}")
    
    generate_markdown(aligned, output_md_path)
    print(f"   [+] Transcript MD: {Path(output_md_path).name}")
    
    generate_jsonl(aligned, output_jsonl_path)
    print(f"   [+] Transcript JSONL: {Path(output_jsonl_path).name}")
    
    # Final stats
    avg_conf = sum(s.confidence for s in aligned) / len(aligned)
    print(f"\n[OK] Средняя точность: {avg_conf:.1%}")
    print("\n[+] Готово!\n")


if __name__ == "__main__":
    main()

