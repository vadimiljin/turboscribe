#!/usr/bin/env python3
"""
Simple extractor for Product Review topics.
Extracts topic list and basic structure for manual completion.
"""

import re
import sys
from pathlib import Path


def extract_topics(content):
    """Extract topics from various formats."""
    topics = []
    
    # Pattern 1: "- Topic name (XX:XX - XX:XX)"
    pattern1 = r'^-\s+(.+?)\s*\((\d+:\d+(?::\d+)?)\s*-\s*(\d+:\d+(?::\d+)?)\)'
    matches1 = re.findall(pattern1, content, re.MULTILINE)
    
    for title, start, end in matches1:
        topics.append({
            'title': title.strip(),
            'start': start,
            'end': end,
            'source': 'dash_list'
        })
    
    # Pattern 2: "### N. Topic name"
    pattern2 = r'^###\s+(\d+)\.\s+(.+?)$'
    matches2 = re.findall(pattern2, content, re.MULTILINE)
    
    for num, title in matches2:
        # Try to find time nearby
        section_match = re.search(
            rf'###\s+{num}\.\s+{re.escape(title)}.*?\*\*Время[^:]*:\*\*\s*\(?([\d:]+)\s*-\s*([\d:]+)',
            content,
            re.DOTALL | re.MULTILINE
        )
        start = section_match.group(1) if section_match else "?"
        end = section_match.group(2) if section_match else "?"
        
        topics.append({
            'title': title.strip(),
            'start': start,
            'end': end,
            'source': 'header'
        })
    
    # Pattern 3: Table format (| ... |)
    # Skip for now
    
    return topics


def generate_minimal_template(topics, recording=None):
    """Generate minimal NotebookLM-ready template."""
    
    output = "# Product Review [DATE]\n\n"
    
    if recording:
        output += f"**Recording:** {recording}\n"
        output += "**Passcode:** [if applicable]\n\n"
    
    output += "---\n\n"
    
    for i, topic in enumerate(topics, 1):
        output += f"## {i}. {topic['title']}\n\n"
        output += f"**Время:** {topic['start']} - {topic['end']}\n"
        output += "**Ответственный:** [TODO]\n\n"
        output += "**Что обсуждали:**\n"
        output += "[TODO: 1-2 предложения о контексте]\n\n"
        output += "**Основные моменты:**\n"
        output += "- [TODO: ключевой момент 1]\n"
        output += "- [TODO: ключевой момент 2]\n\n"
        output += "**Решения и задачи:**\n"
        output += "- [TODO: задача 1]\n"
        output += "- [TODO: задача 2]\n\n"
        output += "**Links:**\n"
        output += "- [TODO: JIRA tickets]\n\n"
        output += "---\n\n"
    
    return output


def generate_simple_structure(topics, recording=None):
    """Generate simple structure (just topics list with separators)."""
    
    output = "# Product Review [DATE]\n\n"
    
    if recording:
        output += f"**Recording:** {recording}\n\n"
    
    output += "---\n\n"
    
    for i, topic in enumerate(topics, 1):
        output += f"## {i}. {topic['title']}\n"
        output += f"**Время:** {topic['start']} - {topic['end']}\n\n"
        output += "**Summary:**\n"
        output += "[TODO]\n\n"
        output += "**Action Plan:**\n"
        output += "[TODO]\n\n"
        output += "---\n\n"
    
    return output


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_for_notebooklm.py <input_file> [--full|--simple]")
        print()
        print("Options:")
        print("  --full    Generate full template with all sections")
        print("  --simple  Generate simple structure (default)")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    mode = 'simple'
    
    if len(sys.argv) > 2:
        if '--full' in sys.argv:
            mode = 'full'
        elif '--simple' in sys.argv:
            mode = 'simple'
    
    if not input_file.exists():
        print(f"❌ File not found: {input_file}")
        sys.exit(1)
    
    # Read file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract recording link
    recording_match = re.search(r'https?://[^\s\)]+zoom[^\s\)]+', content)
    recording = recording_match.group(0) if recording_match else None
    
    # Extract topics
    print(f"📄 Processing: {input_file.name}", file=sys.stderr)
    topics = extract_topics(content)
    print(f"✅ Found {len(topics)} topics", file=sys.stderr)
    
    if not topics:
        print("❌ No topics found! Check file format.", file=sys.stderr)
        sys.exit(1)
    
    # Generate output
    if mode == 'full':
        output = generate_minimal_template(topics, recording)
    else:
        output = generate_simple_structure(topics, recording)
    
    # Write to stdout
    print(output)
    
    # Also save topic list
    list_file = input_file.parent / f"{input_file.stem}_topics_list.txt"
    with open(list_file, 'w', encoding='utf-8') as f:
        for i, topic in enumerate(topics, 1):
            f.write(f"{i:2d}. {topic['title']} ({topic['start']} - {topic['end']})\n")
    
    print(f"\n✅ Topics list saved: {list_file.name}", file=sys.stderr)


if __name__ == '__main__':
    main()




