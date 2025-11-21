## speakers.md Structure

+ must have a jsonl twin for local processing

1. **Header Section**
   - Title: "Speaker Directory"
   - Last updated timestamp
   - Total number of speakers
   - Note that it tracks participants across all meetings

2. **Quick Reference Table**
   - Columns: Speaker name, Speaker ID, Number of meetings, Total segments, Active period (first to last appearance)
   - Sorted by total segments (most active first)

3. **Detailed Speaker Profiles**
   For each speaker:
   - **Name** (as a heading)
   - **Speaker ID** (e.g., `spk_dk`)
   - **Also known as** (if there are name variations)
   - **Total Speaking Time**: total segments across all meetings
   - **Average per Meeting**: average segments per meeting
   - **First Appearance**: date of first meeting
   - **Last Appearance**: date of most recent meeting
   - **Meeting History**: list of all meeting IDs they attended (most recent first)

## Purpose

- Project-level file (one file for all meetings)
- Updated after each meeting
- Used for NotebookLM to understand who participated across meetings
- Enables queries like "Which meetings did Dan and Vova both attend?"

The file is generated automatically in the project root when you process meetings, and it aggregates speaker information from all processed meetings in your project.