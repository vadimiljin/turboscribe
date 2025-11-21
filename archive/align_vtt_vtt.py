#!/usr/bin/env python3
"""
VTT-to-VTT Alignment: Better speaker attribution using resegmented VTT

Key improvement: Uses resegmented VTT (472 segments) instead of TXT (83 blocks)
This reduces granularity gap from 17x to 3x, dramatically improving speaker attribution.
"""

import re
from typing import List, Tuple, Dict
from dataclasses import dataclass
from collections import Counter
from datetime import datetime


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
    confidence: float = 1.0
    match_type: str = "overlap"  # overlap, nearest, fallback


def parse_timestamp(ts: str) -> float:
    """Конвертировать HH:MM:SS.mmm в секунды"""
    # Handle format: 00:02:56.780 or 00:02:56,780
    ts = ts.replace(',', '.')
    parts = ts.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def parse_vtt_with_speakers(filepath: str) -> List[VTTSegment]:
    """Парсинг VTT с именами спикеров (zoom.vtt)"""
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
        
        match = re.search(r'(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})', timestamp_line)
        if not match:
            continue
        
        start = parse_timestamp(match.group(1))
        end = parse_timestamp(match.group(2))
        
        # Extract speaker from first line
        first_line = text_lines[0]
        speaker_match = re.match(r'^([^:]+):\s*(.*)$', first_line)
        
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            text = speaker_match.group(2)
            if len(text_lines) > 1:
                text = text + ' ' + ' '.join(text_lines[1:])
        else:
            speaker = "Unknown"
            text = ' '.join(text_lines)
        
        text = text.strip()
        if text:
            segments.append(VTTSegment(start=start, end=end, speaker=speaker, text=text))
    
    return segments


def parse_vtt_without_speakers(filepath: str) -> List[VTTSegment]:
    """Парсинг VTT без имен спикеров (resegmented.vtt)"""
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
        
        match = re.search(r'(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})', timestamp_line)
        if not match:
            continue
        
        start = parse_timestamp(match.group(1))
        end = parse_timestamp(match.group(2))
        
        text = ' '.join(text_lines).strip()
        
        # Remove TurboScribe watermark
        text = re.sub(r'\(Transcribed by TurboScribe\.ai.*?\)', '', text).strip()
        
        if text:
            segments.append(VTTSegment(start=start, end=end, speaker="", text=text))
    
    return segments


def calculate_overlap(seg1_start: float, seg1_end: float, seg2_start: float, seg2_end: float) -> float:
    """Рассчитать длительность перекрытия между двумя сегментами"""
    overlap_start = max(seg1_start, seg2_start)
    overlap_end = min(seg1_end, seg2_end)
    return max(0, overlap_end - overlap_start)


def align_vtt_to_vtt(speaker_vtt: List[VTTSegment], text_vtt: List[VTTSegment]) -> List[AlignedSegment]:
    """
    Выровнять VTT со спикерами (zoom.vtt) с VTT с текстом (resegmented.vtt)
    
    Strategy:
    1. For each text segment, find all overlapping speaker segments
    2. If single speaker dominates (>70% overlap) - assign all text to them
    3. If multiple speakers - split text proportionally by overlap duration
    """
    aligned = []
    
    for text_seg in text_vtt:
        # Find overlapping speaker segments
        overlaps = []
        
        for spk_seg in speaker_vtt:
            overlap_duration = calculate_overlap(
                spk_seg.start, spk_seg.end,
                text_seg.start, text_seg.end
            )
            
            if overlap_duration > 0:
                overlap_ratio = overlap_duration / (text_seg.end - text_seg.start)
                overlaps.append((spk_seg, overlap_duration, overlap_ratio))
        
        if overlaps:
            # Sort by time (to maintain order)
            overlaps.sort(key=lambda x: x[0].start)
            
            total_overlap = sum(o[1] for o in overlaps)
            
            # Check if single speaker dominates (>70% of text segment)
            # More aggressive threshold to avoid unnecessary splits
            dominant_threshold = 0.70
            if len(overlaps) == 1 or overlaps[0][1] / total_overlap > dominant_threshold:
                # Single speaker gets all text
                best_speaker_seg, best_overlap, best_ratio = overlaps[0]
                
                confidence = min(1.0, best_ratio * 1.05)  # Smaller bonus
                match_type = "single" if len(overlaps) == 1 else "dominant"
                
                aligned.append(AlignedSegment(
                    start=text_seg.start,
                    end=text_seg.end,
                    speaker=best_speaker_seg.speaker,
                    text=text_seg.text,
                    confidence=confidence,
                    match_type=match_type
                ))
            else:
                # Multiple speakers - split text proportionally
                # Split text into sentences/phrases
                text_parts = re.split(r'([.!?]\s+)', text_seg.text)
                # Recombine to keep punctuation with sentences
                sentences = []
                for i in range(0, len(text_parts), 2):
                    if i < len(text_parts):
                        sentence = text_parts[i]
                        if i + 1 < len(text_parts):
                            sentence += text_parts[i + 1]
                        sentences.append(sentence.strip())
                
                sentences = [s for s in sentences if s]
                
                if not sentences:
                    sentences = [text_seg.text]
                
                # Assign sentences to speakers based on overlap proportion
                # Filter out speakers with very small overlap (<15%)
                significant_overlaps = [(s, d, r) for s, d, r in overlaps if d / total_overlap >= 0.15]
                
                if not significant_overlaps:
                    # All overlaps are tiny - just use the first/largest one
                    best_speaker_seg = overlaps[0][0]
                    aligned.append(AlignedSegment(
                        start=text_seg.start,
                        end=text_seg.end,
                        speaker=best_speaker_seg.speaker,
                        text=text_seg.text,
                        confidence=overlaps[0][2] * 0.9,  # Reduced confidence
                        match_type="dominant"
                    ))
                else:
                    # Split only among significant speakers (sentence-based)
                    sentence_idx = 0
                    total_significant = sum(d for _, d, _ in significant_overlaps)
                    
                    for spk_seg, overlap_dur, overlap_ratio in significant_overlaps:
                        # How many sentences should this speaker get?
                        proportion = overlap_dur / total_significant
                        num_sentences = max(1, round(proportion * len(sentences)))
                        
                        # Get sentences for this speaker
                        speaker_sentences = sentences[sentence_idx:sentence_idx + num_sentences]
                        sentence_idx += num_sentences
                        
                        if speaker_sentences:
                            speaker_text = ' '.join(speaker_sentences)
                            
                            # Calculate start/end for this speaker's portion
                            portion_start = max(spk_seg.start, text_seg.start)
                            portion_end = min(spk_seg.end, text_seg.end)
                            
                            # Improved confidence calculation
                            conf_base = overlap_ratio
                            if proportion > 0.5:  # Dominant in split
                                conf_base = min(0.90, conf_base * 1.05)
                            elif proportion > 0.3:  # Reasonable
                                conf_base = min(0.80, conf_base)
                            else:  # Small share
                                conf_base = conf_base * 0.9
                            
                            aligned.append(AlignedSegment(
                                start=portion_start,
                                end=portion_end,
                                speaker=spk_seg.speaker,
                                text=speaker_text,
                                confidence=conf_base,
                                match_type="split"
                            ))
                        
                        if sentence_idx >= len(sentences):
                            break
        else:
            # No overlap - find nearest speaker within ±10 seconds
            nearest_speaker = None
            min_distance = 10.0
            
            for spk_seg in speaker_vtt:
                # Distance from text segment
                if spk_seg.end < text_seg.start:
                    distance = text_seg.start - spk_seg.end
                elif spk_seg.start > text_seg.end:
                    distance = spk_seg.start - text_seg.end
                else:
                    distance = 0
                
                if distance < min_distance:
                    min_distance = distance
                    nearest_speaker = spk_seg
            
            if nearest_speaker:
                # Use nearest speaker with low confidence
                aligned.append(AlignedSegment(
                    start=text_seg.start,
                    end=text_seg.end,
                    speaker=nearest_speaker.speaker,
                    text=text_seg.text,
                    confidence=0.5 - (min_distance / 20),  # Decreases with distance
                    match_type="nearest"
                ))
            else:
                # Fallback: Unknown speaker
                aligned.append(AlignedSegment(
                    start=text_seg.start,
                    end=text_seg.end,
                    speaker="Unknown",
                    text=text_seg.text,
                    confidence=0.0,
                    match_type="fallback"
                ))
    
    return aligned


def format_time(seconds: float) -> str:
    """Форматировать в MM:SS"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def format_time_verbose(seconds: float) -> str:
    """Форматировать в HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def generate_compact_markdown(segments: List[AlignedSegment]) -> str:
    """Генерация компактного Markdown с группировкой по спикерам"""
    lines = []
    
    # Заголовок
    lines.append("# Транскрипт встречи")
    lines.append("")
    lines.append(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    if segments:
        total_duration = segments[-1].end - segments[0].start
        lines.append(f"**Длительность:** {format_time_verbose(total_duration)}")
        speakers = set(seg.speaker for seg in segments)
        lines.append(f"**Участники:** {len(speakers)}")
        avg_conf = sum(s.confidence for s in segments) / len(segments)
        lines.append(f"**Точность:** {avg_conf:.1%}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Группировка последовательных сегментов одного спикера
    grouped = []
    current_group = None
    
    for seg in segments:
        if current_group is None or current_group['speaker'] != seg.speaker:
            # Новый спикер - сохранить предыдущую группу
            if current_group is not None:
                grouped.append(current_group)
            
            # Начать новую группу
            current_group = {
                'speaker': seg.speaker,
                'start': seg.start,
                'end': seg.end,
                'texts': [seg.text]
            }
        else:
            # Тот же спикер - добавить к группе
            current_group['end'] = seg.end
            current_group['texts'].append(seg.text)
    
    # Добавить последнюю группу
    if current_group is not None:
        grouped.append(current_group)
    
    # Генерация вывода (БЕЗ промежуточных меток времени)
    for group in grouped:
        # Склеить все тексты одного спикера в одну строку
        # Убираем точки в конце каждого сегмента, затем соединяем с ". "
        texts = []
        for text in group['texts']:
            text = text.strip()
            # Убираем точку в конце, если есть
            if text.endswith('.'):
                text = text[:-1]
            texts.append(text)
        
        combined_text = '. '.join(texts) + '.'
        
        # Форматирование таймстампа спикера
        start_time = format_time_verbose(group['start'])
        end_time = format_time_verbose(group['end'])
        
        # Вывод: **Спикер** [timestamp]: текст
        lines.append(f"**{group['speaker']}** [{start_time} - {end_time}]: {combined_text}")
        lines.append("")  # Пустая строка между спикерами
    
    return '\n'.join(lines)


def generate_jsonl(segments: List[AlignedSegment], output_path: str):
    """Генерация JSONL для внутренней обработки"""
    import json
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            obj = {
                "start": seg.start,
                "end": seg.end,
                "speaker": seg.speaker,
                "text": seg.text,
                "confidence": round(seg.confidence, 3),
                "match_type": seg.match_type,
                "duration": round(seg.end - seg.start, 2)
            }
            f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def generate_statistics(segments: List[AlignedSegment]) -> str:
    """Генерация статистики"""
    lines = []
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Статистика")
    lines.append("")
    
    # Спикеры
    speaker_stats = Counter(seg.speaker for seg in segments)
    speaker_times = {}
    speaker_confidences = {}
    
    for seg in segments:
        duration = seg.end - seg.start
        speaker_times[seg.speaker] = speaker_times.get(seg.speaker, 0) + duration
        if seg.speaker not in speaker_confidences:
            speaker_confidences[seg.speaker] = []
        speaker_confidences[seg.speaker].append(seg.confidence)
    
    lines.append("### Участники")
    lines.append("")
    
    for speaker, count in speaker_stats.most_common():
        time = speaker_times[speaker]
        percentage = (time / sum(speaker_times.values())) * 100
        avg_conf = sum(speaker_confidences[speaker]) / len(speaker_confidences[speaker])
        lines.append(f"- **{speaker}**: {count} сегментов, {format_time_verbose(time)} ({percentage:.1f}%), точность {avg_conf:.1%}")
    
    lines.append("")
    
    # Общая инфо
    lines.append("### Качество выравнивания")
    lines.append("")
    
    total_segments = len(segments)
    match_types = Counter(seg.match_type for seg in segments)
    
    lines.append(f"- Всего сегментов: {total_segments}")
    lines.append(f"- Одиночное совпадение: {match_types.get('single', 0)} ({match_types.get('single', 0)/total_segments*100:.1f}%)")
    lines.append(f"- Доминирующий спикер: {match_types.get('dominant', 0)} ({match_types.get('dominant', 0)/total_segments*100:.1f}%)")
    lines.append(f"- Разделено между спикерами: {match_types.get('split', 0)} ({match_types.get('split', 0)/total_segments*100:.1f}%)")
    lines.append(f"- Ближайший (нет совпадения): {match_types.get('nearest', 0)} ({match_types.get('nearest', 0)/total_segments*100:.1f}%)")
    
    avg_confidence = sum(seg.confidence for seg in segments) / len(segments)
    lines.append(f"- Средняя уверенность: {avg_confidence:.1%}")
    
    low_conf = [seg for seg in segments if seg.confidence < 0.7]
    if low_conf:
        lines.append(f"- ⚠️ Низкая уверенность (<70%): {len(low_conf)} сегментов ({len(low_conf)/total_segments*100:.1f}%)")
    
    lines.append("")
    
    return '\n'.join(lines)


def main():
    print("=" * 80)
    print("VTT-TO-VTT ВЫРАВНИВАНИЕ (Improved Speaker Attribution)")
    print("=" * 80)
    print()
    
    # Пути
    speaker_vtt_path = "/home/vadim/Projects/route4me.com/turboscribe/zoom.vtt"
    text_vtt_path = "/home/vadim/Projects/route4me.com/turboscribe/GMT20251106-142611 Recording.vtt"
    output_md_path = "/home/vadim/Projects/route4me.com/turboscribe/vtt_aligned_transcript.md"
    output_jsonl_path = "/home/vadim/Projects/route4me.com/turboscribe/vtt_aligned_transcript.jsonl"
    
    # Парсинг
    print("📖 Чтение VTT с именами спикеров (zoom.vtt)...")
    speaker_vtt = parse_vtt_with_speakers(speaker_vtt_path)
    print(f"   ✓ {len(speaker_vtt)} сегментов с спикерами")
    print(f"   ✓ Средняя длина: {sum(s.end - s.start for s in speaker_vtt) / len(speaker_vtt):.1f} сек")
    
    unique_speakers = set(s.speaker for s in speaker_vtt)
    print(f"   ✓ Уникальных спикеров: {len(unique_speakers)}")
    print(f"   ✓ Спикеры: {', '.join(sorted(unique_speakers))}")
    
    print("\n📖 Чтение VTT с чистым текстом (resegmented.vtt)...")
    text_vtt = parse_vtt_without_speakers(text_vtt_path)
    print(f"   ✓ {len(text_vtt)} сегментов с текстом")
    print(f"   ✓ Средняя длина: {sum(s.end - s.start for s in text_vtt) / len(text_vtt):.1f} сек")
    
    # Анализ гранулярности
    speaker_avg_duration = sum(s.end - s.start for s in speaker_vtt) / len(speaker_vtt)
    text_avg_duration = sum(s.end - s.start for s in text_vtt) / len(text_vtt)
    granularity_ratio = text_avg_duration / speaker_avg_duration
    
    print(f"\n📊 Анализ гранулярности:")
    print(f"   ✓ Zoom VTT: {len(speaker_vtt)} сегментов @ {speaker_avg_duration:.1f}с")
    print(f"   ✓ Resegmented VTT: {len(text_vtt)} сегментов @ {text_avg_duration:.1f}с")
    print(f"   ✓ Соотношение: {granularity_ratio:.1f}x (было 17x с TXT!)")
    
    # Выравнивание
    print("\n🔄 Выравнивание спикеров с текстом...")
    aligned = align_vtt_to_vtt(speaker_vtt, text_vtt)
    print(f"   ✓ {len(aligned)} выровненных сегментов")
    
    # Генерация
    print("\n📝 Генерация выходных файлов...")
    markdown = generate_compact_markdown(aligned)
    statistics = generate_statistics(aligned)
    
    full_content = markdown + "\n" + statistics
    
    # Сохранение
    with open(output_md_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    print(f"   ✓ Markdown: {output_md_path}")
    
    generate_jsonl(aligned, output_jsonl_path)
    print(f"   ✓ JSONL: {output_jsonl_path}")
    
    # Краткая статистика
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 80)
    
    speaker_counts = Counter(seg.speaker for seg in aligned)
    print(f"\n👥 Участники ({len(speaker_counts)}):")
    for speaker, count in speaker_counts.most_common():
        print(f"   {speaker}: {count} сегментов")
    
    if aligned:
        avg_conf = sum(s.confidence for s in aligned) / len(aligned)
        print(f"\n✅ Средняя точность: {avg_conf:.1%}")
        
        match_types = Counter(s.match_type for s in aligned)
        print(f"\n📊 Качество совпадений:")
        print(f"   Отличное (single): {match_types.get('single', 0)} ({match_types.get('single', 0)/len(aligned)*100:.1f}%)")
        print(f"   Хорошее (dominant): {match_types.get('dominant', 0)} ({match_types.get('dominant', 0)/len(aligned)*100:.1f}%)")
        print(f"   Разделено (split): {match_types.get('split', 0)} ({match_types.get('split', 0)/len(aligned)*100:.1f}%)")
        print(f"   Низкое (nearest): {match_types.get('nearest', 0)} ({match_types.get('nearest', 0)/len(aligned)*100:.1f}%)")
        
        low_conf = [seg for seg in aligned if seg.confidence < 0.7]
        if low_conf:
            print(f"\n⚠️  Требуют проверки: {len(low_conf)} сегментов ({len(low_conf)/len(aligned)*100:.1f}%)")
    
    print(f"\n✓ Готово!")
    print()


if __name__ == "__main__":
    main()

