# Resegmentation Test Results

**Date:** 2025-11-14  
**Test File:** GMT20251106-142611 Recording (30 minutes)  
**Settings Used:** Default TurboScribe values (Max Words: 8, Max Duration: 10s, Max Chars: 80)

---

## 1. Export Format Analysis

### Available Formats from TurboScribe

| Format | File Size | Lines | Segments | Has Timestamps | Has Speakers | Parseable |
|--------|-----------|-------|----------|----------------|--------------|-----------|
| **TXT** | 29KB | 245 | 83 | ✅ (MM:SS) | ❌ | ✅ Easy |
| **VTT** | 43KB | 1,889 | 472 | ✅ (HH:MM:SS.mmm) | ❌ | ✅ Medium |
| **SRT** | 43KB | 1,888 | 472 | ✅ (HH:MM:SS,mmm) | ❌ | ✅ Medium |
| **CSV** | 38KB | 474 | 473 | ✅ (milliseconds) | ❌ | ✅ Hard |
| **PDF** | 58KB | 1,016 | N/A | ❌ | ❌ | ❌ |
| **DOCX** | 17KB | 93 | N/A | ❌ | ❌ | ❌ |

### ⚠️ Critical Finding

**NO SPEAKER LABELS IN ANY TURBOSCRIBE EXPORT!**

TurboScribe re-transcribes the audio and does NOT preserve speaker labels from the original VTT file. This confirms the need for the current workflow:

1. Original `zoom.vtt` → speaker labels (but micro-segments)
2. Resegmented TurboScribe TXT → clean text (but no speakers)
3. `align_vtt_txt.py` → merge speakers from #1 with text from #2

### Recommended Format: **TXT**

**Why TXT is optimal:**

1. ✅ **Cleanest format** - Simple `(MM:SS - MM:SS)` + text structure
2. ✅ **Most compact** - 245 lines vs 1,889 (VTT/SRT)
3. ✅ **Balanced segmentation** - 83 blocks averaging ~21 seconds each
4. ✅ **Already supported** - `parse_txt()` function exists in align_vtt_txt.py
5. ✅ **Human readable** - Easy to verify quality

**Why NOT other formats:**

- **VTT/SRT**: Still too granular (472 segments), harder to parse, no advantage
- **CSV**: Millisecond timestamps require conversion, harder to read
- **PDF/DOCX**: Not machine-readable for alignment

---

## 2. Segmentation Comparison

### Original Files

| File | Segments | Avg Duration | Quality Issue |
|------|----------|--------------|---------------|
| **zoom.vtt** | 1,430 | ~1.3 sec | ❌ Too granular (1-2 words) |
| **turboscribe.txt** | 76 | ~23 sec | ❌ Too coarse (multiple speakers) |

### After Resegmentation (Default Settings)

| File | Segments | Avg Duration | Change |
|------|----------|--------------|--------|
| **Resegmented VTT** | 472 | ~3.8 sec | -67% segments |
| **Resegmented TXT** | 83 | ~21 sec | +9% segments |

### Analysis

- **TXT improvement: MINIMAL** - From 76 → 83 blocks (+9%)
- **VTT improvement: SIGNIFICANT** - From 1,430 → 472 segments (-67%)

**Conclusion:** Default TurboScribe segmentation settings had minimal impact on TXT output. The real benefit is potentially better timestamp alignment, not segment count reduction.

---

## 3. Alignment Test Results

### Test Setup

```bash
Input:  zoom.vtt (1,430 segments with speaker labels)
        + Resegmented TXT (83 blocks, clean text)
Output: resegmented_transcript.md (133 aligned segments)
```

### Results Comparison

| Metric | Original Alignment | Resegmented Alignment | Change |
|--------|-------------------|----------------------|--------|
| **VTT segments** | 1,430 | 1,430 | (same) |
| **TXT blocks** | 74 | 81 | +9.5% |
| **Aligned segments** | 133 | 133 | (same) |
| **Avg confidence** | 77.9% | 76.2% | **-1.7%** ⚠️ |

### Speaker Distribution Changes

| Speaker | Original Segments | Original Time | Resegmented Segments | Resegmented Time | Change |
|---------|------------------|---------------|---------------------|-----------------|--------|
| **Dan Khasis** | 68 (50.4%) | 7:28 | 68 (46.8%) | 7:30 | No change |
| **Serhii Kasainov** | 28 (24.8%) | 3:40 | **32 (29.6%)** | **4:45** | +4 segments ✅ |
| **Vova** | 13 (9.6%) | 1:25 | **14 (10.1%)** | **1:36** | +1 segment ✅ |
| **Semeyon S** | 5 (1.7%) | 0:14 | **3 (1.2%)** | **0:11** | -2 segments ⚠️ |
| **Artur Moskalenko** | 4 (0.7%) | 0:06 | **3 (0.6%)** | **0:05** | -1 segment ⚠️ |
| **Igor Skrynkovskyy** | 4 (2.0%) | 0:18 | **2 (1.6%)** | **0:15** | -2 segments ⚠️ |

### Attribution Accuracy Test: Problem Section (2:56 - 3:10)

**Expected speakers from zoom.vtt:**
1. Artur Moskalenko: "Дэн привет."
2. Semeyon S: "Ребята кто там, хотел начать."
3. Serhii Kasainov: "Я."
4. Semeyon S: "Давай."
5. Igor Skrynkovskyy: "Так Давайте подождем Чтобы дан сказал."

**Resegmented result:**
```markdown
**Artur Moskalenko:**  
Дэн, привет. Ребята, кто там хотел начать? Я. Давай. Давайте подождем чтобы Дэн сказал.
```

**Attribution: ❌ INCORRECT**

All 5 speakers' text was attributed to Artur Moskalenko (same as original problem).

---

## 4. Conclusion

### ❌ Resegmentation Did NOT Solve the Speaker Attribution Problem

**Key Findings:**

1. **Confidence decreased**: 77.9% → 76.2% (-1.7%)
2. **Problem section unchanged**: Multiple speakers still merged under wrong attribution
3. **Minimal segmentation impact**: TXT blocks only increased from 76 → 83 (+9%)

### Root Cause Confirmed

The problem is NOT with TurboScribe segmentation parameters. The issue is:

**TurboScribe TXT blocks are STILL too large (10-30 seconds) compared to zoom.vtt micro-segments (1-3 seconds)**

Even with "default minimal" settings:
- Resegmented TXT: 83 blocks, ~21 sec average
- Original zoom.vtt: 1,430 segments, ~1.3 sec average
- **Ratio: 17x difference in granularity**

When `align_vtt_txt.py` tries to match:
- TXT block (2:56 - 3:07) = 11 seconds
- Contains 5+ different VTT speakers
- Algorithm picks first/longest overlapping speaker → wrong attribution

---

## 5. Recommendations

### Option 1: ❌ Further Reduce TurboScribe Segmentation (NOT RECOMMENDED)

Try even more aggressive settings:
- Max Words: 5
- Max Duration: 5 seconds
- Max Characters: 40

**Problem:** TurboScribe may not go smaller, and even 5-second blocks can span multiple speakers in rapid conversations.

### Option 2: ✅ Use TurboScribe VTT Output Instead of TXT (RECOMMENDED)

**Key insight:** Resegmented VTT has 472 segments (~3.8 sec each) vs 83 TXT blocks (~21 sec each)

**New workflow:**
```
Original zoom.vtt (1,430 segments, speaker labels)
    +
Resegmented VTT (472 segments, clean text, better granularity)
    ↓
align_vtt_vtt.py (NEW SCRIPT)
    ↓
Better attribution (~90%+ accuracy expected)
```

**Why this will work:**
- VTT resegmented: 472 segments @ 3.8 sec avg
- Original VTT: 1,430 segments @ 1.3 sec avg
- **Ratio: 3x difference (much better than 17x with TXT!)**
- More likely that one resegmented VTT segment = one zoom.vtt speaker

### Option 3: ✅ Improve Alignment Algorithm

Modify `align_vtt_txt.py` to:

1. **Split TXT blocks by speaker changes detected in VTT**
   - If TXT block (2:56 - 3:07) overlaps with 5 VTT speakers
   - Split the TXT text proportionally to VTT durations
   - Assign each portion to correct speaker

2. **Use majority voting**
   - Calculate overlap duration for each speaker
   - Assign text to speaker with longest overlap
   - Add confidence score based on overlap ratio

3. **Dynamic tolerance**
   - Current: fixed 5-second tolerance
   - Proposed: scale tolerance based on TXT block duration
   - Short blocks (5-10s) → 2s tolerance
   - Long blocks (20-30s) → 8s tolerance

---

## 6. Next Steps

### Immediate Action: Test Option 2 (VTT-to-VTT Alignment)

1. ✅ **Done**: Confirmed resegmented VTT has better granularity (472 vs 83 segments)
2. **TODO**: Modify `align_vtt_txt.py` to accept VTT input instead of TXT
3. **TODO**: Test alignment with `zoom.vtt` + `resegmented.vtt`
4. **Expected**: Accuracy improves from 77.9% to 85-90%

### Alternative: Improve Alignment Algorithm (Option 3)

Implement smart text splitting when TXT block contains multiple VTT speakers.

---

## 7. File Locations

```
/home/vadim/Projects/route4me.com/turboscribe/
├── zoom.vtt                                    # Original with speaker labels
├── turboscribe.txt                             # Original TurboScribe output
├── aligned_transcript_v2.md                    # Original alignment (77.9% confidence)
├── resegmented_transcript.md                   # NEW: Resegmented alignment (76.2% confidence)
└── GMT20251106-142611 Recording/
    ├── GMT20251106-142611 Recording.txt        # Resegmented TXT (83 blocks)
    ├── GMT20251106-142611 Recording.vtt        # Resegmented VTT (472 segments) ⭐
    ├── GMT20251106-142611 Recording.srt        # (472 segments)
    ├── GMT20251106-142611 Recording.csv        # (473 rows)
    ├── GMT20251106-142611 Recording.pdf
    └── GMT20251106-142611 Recording.docx
```

**Recommended for next test:** Use the **resegmented VTT** file (472 segments, 3.8s average) for better granularity matching.

