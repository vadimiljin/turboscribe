#!/usr/bin/env python3
"""
Улучшенная версия выравнивания с дополнительными фичами
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
class TXTBlock:
    start: float
    end: float
    text: str


@dataclass
class AlignedSegment:
    start: float
    end: float
    speaker: str
    text: str
    confidence: float = 1.0


def parse_timestamp(ts: str) -> float:
    """Конвертировать в секунды"""
    parts = ts.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def parse_vtt(filepath: str) -> List[VTTSegment]:
    """Парсинг VTT файла"""
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
        
        segments.append(VTTSegment(start=start, end=end, speaker=speaker, text=text))
    
    return segments


def parse_txt(filepath: str) -> List[TXTBlock]:
    """Парсинг TXT файла"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = []
    pattern = r'\((\d+:\d+)\s*-\s*(\d+:\d+)\)\s*\n(.*?)(?=\n\(\d+:\d+\s*-|\Z)'
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for match in matches:
        start = parse_timestamp(match.group(1))
        end = parse_timestamp(match.group(2))
        text = match.group(3).strip()
        blocks.append(TXTBlock(start=start, end=end, text=text))
    
    return blocks


def split_text_smartly(text: str) -> List[str]:
    """Умное разбиение текста на фразы"""
    # Разбить по точкам, вопросам, восклицаниям
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Объединить очень короткие фразы
    result = []
    buffer = ""
    
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        
        if len(buffer) > 0:
            buffer += " " + sent
        else:
            buffer = sent
        
        # Если буфер достаточно длинный или это последнее предложение
        if len(buffer) > 100 or sent == sentences[-1]:
            result.append(buffer)
            buffer = ""
    
    if buffer:
        result.append(buffer)
    
    return result


def align_segments(vtt_segments: List[VTTSegment], txt_blocks: List[TXTBlock]) -> List[AlignedSegment]:
    """Выровнять VTT спикеров с TXT текстом"""
    aligned = []
    
    for txt_block in txt_blocks:
        # Найти VTT сегменты в этом временном диапазоне
        tolerance = 5.0  # секунды
        overlapping_vtt = []
        
        for vtt in vtt_segments:
            if not (vtt.end < txt_block.start - tolerance or vtt.start > txt_block.end + tolerance):
                overlap_start = max(vtt.start, txt_block.start)
                overlap_end = min(vtt.end, txt_block.end)
                overlap_duration = max(0, overlap_end - overlap_start)
                
                if overlap_duration > 0:
                    overlapping_vtt.append((vtt, overlap_duration))
        
        if not overlapping_vtt:
            continue
        
        # Сортировать по времени
        overlapping_vtt.sort(key=lambda x: x[0].start)
        
        # Разбить текст на умные фразы
        phrases = split_text_smartly(txt_block.text)
        
        if not phrases:
            continue
        
        # Распределить фразы по VTT сегментам
        total_vtt_duration = sum(overlap for _, overlap in overlapping_vtt)
        chars_per_second = len(txt_block.text) / total_vtt_duration if total_vtt_duration > 0 else 0
        
        phrase_idx = 0
        
        for vtt, overlap in overlapping_vtt:
            if phrase_idx >= len(phrases):
                break
            
            # Сколько символов можем уместить
            vtt_duration = vtt.end - vtt.start
            estimated_chars = int(vtt_duration * chars_per_second * 1.3)  # +30% буфер
            
            segment_text = ""
            phrases_used = 0
            
            while phrase_idx < len(phrases) and len(segment_text + phrases[phrase_idx]) <= estimated_chars:
                if segment_text:
                    segment_text += " "
                segment_text += phrases[phrase_idx]
                phrase_idx += 1
                phrases_used += 1
            
            # Если не удалось уместить ни одной фразы, берем хотя бы одну
            if not segment_text and phrase_idx < len(phrases):
                segment_text = phrases[phrase_idx]
                phrase_idx += 1
                phrases_used = 1
            
            if segment_text:
                # Рассчитать confidence на основе overlap
                confidence = min(1.0, overlap / vtt_duration) if vtt_duration > 0 else 0.5
                
                aligned.append(AlignedSegment(
                    start=vtt.start,
                    end=vtt.end,
                    speaker=vtt.speaker,
                    text=segment_text,
                    confidence=confidence
                ))
    
    # Сортировка по времени
    aligned.sort(key=lambda x: x.start)
    
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


def generate_markdown(segments: List[AlignedSegment]) -> str:
    """Генерация Markdown транскрипта"""
    lines = []
    
    # Заголовок
    lines.append("# Выровненный транскрипт встречи")
    lines.append("")
    lines.append(f"**Дата обработки:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    if segments:
        total_duration = segments[-1].end - segments[0].start
        lines.append(f"**Длительность:** {format_time_verbose(total_duration)}")
        
        speakers = set(seg.speaker for seg in segments)
        lines.append(f"**Участники:** {len(speakers)}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Транскрипт
    last_speaker = None
    last_timestamp = 0
    
    for seg in segments:
        # Временные метки каждые 2 минуты
        if seg.start - last_timestamp >= 120:
            lines.append("")
            lines.append(f"### [{format_time(seg.start)}]")
            lines.append("")
            last_timestamp = seg.start
        
        # Смена спикера
        if seg.speaker != last_speaker:
            lines.append("")
            lines.append(f"**{seg.speaker}:**  ")
            last_speaker = seg.speaker
        
        lines.append(seg.text)
        lines.append("")
    
    return '\n'.join(lines)


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
    
    for seg in segments:
        duration = seg.end - seg.start
        speaker_times[seg.speaker] = speaker_times.get(seg.speaker, 0) + duration
    
    lines.append("### Участники")
    lines.append("")
    
    for speaker, count in speaker_stats.most_common():
        time = speaker_times[speaker]
        percentage = (time / sum(speaker_times.values())) * 100
        lines.append(f"- **{speaker}**: {count} сегментов, {format_time_verbose(time)} ({percentage:.1f}%)")
    
    lines.append("")
    
    # Общая инфо
    lines.append("### Общая информация")
    lines.append("")
    lines.append(f"- Всего сегментов: {len(segments)}")
    lines.append(f"- Всего участников: {len(speaker_stats)}")
    
    if segments:
        total_duration = segments[-1].end - segments[0].start
        lines.append(f"- Общая длительность: {format_time_verbose(total_duration)}")
        
        avg_confidence = sum(seg.confidence for seg in segments) / len(segments)
        lines.append(f"- Средняя уверенность выравнивания: {avg_confidence:.1%}")
    
    lines.append("")
    
    return '\n'.join(lines)


def main():
    print("=" * 80)
    print("УЛУЧШЕННОЕ ВЫРАВНИВАНИЕ VTT + TXT")
    print("=" * 80)
    print()
    
    # Пути
    vtt_path = "/home/vadim/Projects/route4me.com/turboscribe/zoom.vtt"
    txt_path = "/home/vadim/Projects/route4me.com/turboscribe/GMT20251106-142611 Recording/GMT20251106-142611 Recording.txt"
    output_path = "/home/vadim/Projects/route4me.com/turboscribe/resegmented_transcript.md"
    
    # Парсинг
    print("📖 Чтение VTT файла...")
    vtt_segments = parse_vtt(vtt_path)
    print(f"   ✓ {len(vtt_segments)} сегментов с спикерами")
    
    print("📖 Чтение TXT файла...")
    txt_blocks = parse_txt(txt_path)
    print(f"   ✓ {len(txt_blocks)} блоков с чистым текстом")
    
    # Выравнивание
    print("\n🔄 Выравнивание по временным меткам...")
    aligned = align_segments(vtt_segments, txt_blocks)
    print(f"   ✓ {len(aligned)} выровненных сегментов")
    
    # Генерация
    print("\n📝 Генерация Markdown...")
    markdown = generate_markdown(aligned)
    statistics = generate_statistics(aligned)
    
    full_content = markdown + "\n" + statistics
    
    # Сохранение
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    print(f"   ✓ Сохранено в: {output_path}")
    
    # Краткая статистика
    print("\n" + "=" * 80)
    print("КРАТКАЯ СТАТИСТИКА")
    print("=" * 80)
    
    speaker_counts = Counter(seg.speaker for seg in aligned)
    print(f"\n👥 Участники ({len(speaker_counts)}):")
    for speaker, count in speaker_counts.most_common():
        print(f"   {speaker}: {count} сегментов")
    
    if aligned:
        total_duration = aligned[-1].end - aligned[0].start
        print(f"\n⏱ Длительность: {format_time_verbose(total_duration)}")
        avg_conf = sum(s.confidence for s in aligned) / len(aligned)
        print(f"✅ Средняя уверенность: {avg_conf:.1%}")
    
    print(f"\n✓ Готово! Файл: {output_path}")
    print()


if __name__ == "__main__":
    main()
