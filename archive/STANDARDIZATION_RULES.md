# Product Review Meeting Notes - Standardization Rules

## ⚠️ CRITICAL PRINCIPLE
**PRESERVE EVERY WORD. DO NOT REMOVE OR CONDENSE ANY CONTENT.**
This is about RESTRUCTURING format for consistency, NOT about summarizing or reducing information.

---

## DOCUMENT STRUCTURE

### SECTION 1: HEADER (REQUIRED)

```markdown
# Product Review [DD MMM YYYY]
```
OR
```markdown  
# Ad Hoc [DD MMM YYYY] ([Brief Topic])
```
OR
```markdown
# Tech-Leads-Chat [DD MMM YYYY]
```
OR (preserve original title format):
```markdown
# Product Progress Review [DD MMM YYYY]
```

**Recording:** [Full Zoom/Drive URL]  
**Passcode:** [if applicable]

------

### SECTION 2: AGENDA (ALWAYS INCLUDE IF EXISTS)

**Important:** Agenda is often at the very top of file, sometimes without "## Agenda" header. ALWAYS add the header.

**Format:**
```markdown
## Agenda

- **[Topic/Feature Name]** - Owner: [Name] ([email])
  - Sub-item if exists
  - Blocked by: [reason] (if mentioned)
  - Ticket: [JIRA link] (if mentioned)
  
- **[Topic/Feature Name]** - Owner: [Name] ([email])
  - Sub-item if exists

## Questions

- [Question text or link] - [Name] ([email])
- [Another question] - [Name] ([email])

------
```

**Key points:**
- Always add `## Agenda` header even if missing in original
- Always add `## Questions` header even if missing in original
- Format: `- **[Topic]** - Owner: [Name] ([email])`
- Remove double brackets like `[[Name]]` - use single: `[Name]`
- Add separator `------` after Questions section

**Example from real file - BEFORE:**
```markdown
# Product Progress Review 3 Nov 2025
https://route4me.zoom.us/rec/share/NT0x8...
Код доступа: PF41yd#X
- Location Snapshot [[Alexey Gusentsov](mailto:alexey.gusentsov@route4me.com)]
  - Tab: Service Time
- Strategic Optimizations
  - Scatter Plot [[Manar Kurmanov](mailto:manar.kurmanov@route4me.com)]
Questions
- https://storage.googleapis.com/... [[Alexey Afanasiev](mailto:alexey@route4me.com)]
- Clarification of priorities, technical debt. [[Semeyon Svetliy](mailto:semeyon@route4me.com)]
```

**AFTER restructuring:**
```markdown
# Product Progress Review 3 Nov 2025

**Recording:** https://route4me.zoom.us/rec/share/NT0x8...
**Passcode:** PF41yd#X

------

## Agenda

- **Location Snapshot** - Owner: Alexey Gusentsov (alexey.gusentsov@route4me.com)
  - Tab: Service Time
  
- **Strategic Optimizations** - Owner: Manar Kurmanov (manar.kurmanov@route4me.com)
  - Scatter Plot

## Questions

- https://storage.googleapis.com/... - Alexey Afanasiev (alexey@route4me.com)
- Clarification of priorities, technical debt - Semeyon Svetliy (semeyon@route4me.com)

------
```

**BETTER Example from real file:**
```markdown

# Product Progress Review 3 Nov 2025
[https://route4me.zoom.us/rec/share/NT0x8XTTlh-iBITelIAgHgLYkOTs4ZwThfaNvjuRb_gwZp5M4ZEX_bXiMDtWFmyo.kcC9rz47JEzJAqKx](https://route4me.zoom.us/rec/share/NT0x8XTTlh-iBITelIAgHgLYkOTs4ZwThfaNvjuRb_gwZp5M4ZEX_bXiMDtWFmyo.kcC9rz47JEzJAqKx)
Код доступа: PF41yd#X

AGENDA STARTS HERE -->

- Location Snapshot [[Alexey Gusentsov](mailto:alexey.gusentsov@route4me.com)]
  - Tab: Service Time
- Strategic Optimizations
  - Scatter Plot [[Manar Kurmanov](mailto:manar.kurmanov@route4me.com)]
- Timezone [[Serhii Kasainov](mailto:kserhii@route4me.com), [Davron Usmonov](mailto:davronu@route4me.com)]
- Connection Snapshot
  - Items [[Davron Usmonov](mailto:davronu@route4me.com)]
  - Pricing [[Serhii Kasainov](mailto:kserhii@route4me.com)]
Questions
- [https://storage.googleapis.com/tech-leads-images/C06V7T5831D_1761941178.486709_1.png](https://storage.googleapis.com/tech-leads-images/C06V7T5831D_1761941178.486709_1.png) [[Alexey Afanasiev](mailto:alexey@route4me.com)]
- Clarification of priorities, technical debt. [[Semeyon Svetliy](mailto:semeyon@route4me.com)]
- “SSO Registration still broken” - to discuss with Dan  [[Artur Moskalenko](mailto:arturm@route4me.com)]
- Recurly Prod access for billing tests [[Artur Moskalenko](mailto:arturm@route4me.com)]

<-- AGENDA ENDS HERE

## Отчет о стратегическом совещании команды
Дата: 3 ноября 2025 г.
Присутствовали: 
```


---

### SECTION 3: MEETING REPORT HEADER (if detailed notes exist)

```markdown
## Отчет о [strategic/product review/etc] совещании команды

**Дата:** [DD month YYYY г.] (copy exact format)  
**Время:** [if available]  
**Присутствовали:** [List all names exactly as in original, separated by commas]  
**Документ подготовил:** [if mentioned]  
**Цель встречи:** [Copy exact goal statement from original, if exists]

------
```

**Important:** Add separator `------` after this section.

### SECTION 4: TOPIC DISCUSSIONS

**Add this header before topics:**
```markdown
## Темы обсуждения

*(Note about transformation, if needed)*

------
```

**Every discussed topic MUST use this structure:**

```markdown
### [N]. [Full Topic Title from Original - copy exactly, including prefix like "Обсуждение:"]

**Topic:** [Topic name if it was in separate field]  
**Ответственный/Responsible:** [Name(s)] [preserve original field label if exists]  
**Время обсуждения:** [Copy exact timestamp from source: (MM:SS), (MM:SS - MM:SS), HH:MM:SS – HH:MM:SS, etc.] [preserve original field label if exists]  
**Priority:** [only if explicitly mentioned]

#### Контекст / Цель
[COPY EXACT TEXT explaining what was discussed and why. Do not shorten.]

#### Ключевые моменты обсуждения и предложения команды
[COPY ALL discussion points. Use numbered list if original used numbers, bullets otherwise:]
1. **[Label before colon]:** [Point 1 - full text with label if exists, e.g., "**Данные:** ..."]
2. **[Label]:** [Point 2 - full text]
3. [Continue with all points]

**Important:** If a point starts with a label followed by colon (e.g., "Статус Invoices:", "Item Master:", "Цель:"), make the label **bold** to highlight it for training purposes.

#### Ключевые тезисы, директивы и мнения Дэна
[COPY ALL leadership statements. Use numbered list if original used numbers:]
1. [Directive 1 - full text with any inline timestamps like (11:34)]
2. [Business rationale - full text]
3. [Continue with all points]

**⚠️ IMPORTANT:** 
- If text contains inline numbered lists (e.g., "1) xxx 2) yyy"), convert to proper markdown numbered list format
- **Name correction:** In English text, ALWAYS use "Dan", "Dan's", "Dan said" - NEVER "Den" or "Ден" in English context

#### Решения и План Действий / Следующие шаги
[COPY ALL decisions and action items. Use numbered list if original used numbers:]
1. ([Responsible]) [Exact task description]
2. ([Responsible]) [Another task]
- Or use format: **[Person Name]**: [Task] if more appropriate

#### Итоговое резюме по теме
[COPY exact summary from original. If no summary exists, write one that captures ALL key points from the topic.]

------
```

**Important:** 
- If original had table format for parameters, convert to field format but preserve ALL content
- Use `------` separator between topics
- Preserve ALL field names from original (Topic, Responsible, Time discussed, etc.)
- Preserve numbered lists if original used them
- Keep inline timestamps within text (e.g., "(11:34)")

---

## FORMATTING RULES

### Language
- **Keep original language** (Russian or English)
- **DO NOT translate**

### Names
- **Format:** `[Full Name](mailto:email@example.com)` in Agenda and first mention
- **Subsequent mentions:** Use first name or as used in original
- **Preserve role mentions:** "Dan Khasis (CEO)", "Igor Skrynkovskyy"
- **⚠️ CRITICAL - CEO Name:** 
  - **In English text:** ALWAYS write "Dan", "Dan's", "Dan said", etc. NEVER use "Den" or "Ден" in English context
  - **In Russian text:** Use "Дэн" (Russian transliteration is acceptable in Russian context)
  - **Examples:** 
    - ✅ "Dan said it's critical" (English)
    - ✅ "Дэн сказал, что это критично" (Russian)
    - ❌ "Den said it's critical" (WRONG - never use "Den" in English)
    - ❌ "Dan's directive" → "Den's directive" (WRONG)

### Links
- **Always preserve all links**
- **Format:** `[Descriptive text or ticket ID](full URL)`
- **JIRA:** `[TICKET-123](https://route4me.atlassian.net/browse/TICKET-123)`

### Timestamps
- **⚠️ CRITICAL: ALWAYS PRESERVE ALL TIMESTAMPS**
- Timestamps are from video recordings and are essential for reference
- **Common formats in source files:**
  - `(11:34)` - single timestamp
  - `(14:25 - 14:30)` - range with spaces and dash
  - `06:13 – 18:48` - range with en-dash
  - `00:15:47 – 00:26:54` - full format
- **Preserve original format** - don't standardize
- Place in **Время обсуждения:** or **Time:** field in topic sections

### Lists
- Use `-` for unordered bullets
- Use `1. 2. 3.` for numbered sequences  
- Indent sub-items with 2 spaces
- **Preserve original list structure**
- **⚠️ CRITICAL - Inline Numbered Lists:** If text contains numbered items in a single line (e.g., "1) xxx 2) yyy 3) zzz" or "1. xxx 2. yyy 3. zzz"), convert them to proper markdown numbered list format with each item on a separate line:

**BEFORE (inline numbered list):**
```markdown
Озвучены приоритеты: 1) Закончить исправления UI (вероятно, связанные с ассайнментом/диспетчем). 2) Экспорт по кастомным полям. 3) Для BlumNet: инвайты, обработка ордеров.
```

**AFTER (proper markdown numbered list):**
```markdown
Озвучены приоритеты:

1. Закончить исправления UI (вероятно, связанные с ассайнментом/диспетчем)
2. Экспорт по кастомным полям
3. Для BlumNet: инвайты, обработка ордеров
```

**Patterns to detect and convert:**
- `1) 2) 3)` → numbered list
- `1. xxx 2. yyy 3. zzz` → numbered list
- `1) xxx 2. yyy 3) zzz` (mixed) → numbered list
- Always put each numbered item on its own line
- Preserve the text before the list (e.g., "Озвучены приоритеты:")

### Emphasis
- **Bold** for: Names in action items, "Ответственный", "Responsible", keywords, field names like **Recording:**, **Passcode:**
- **⚠️ IMPORTANT:** In "Ключевые моменты обсуждения и предложения команды" section, always make labels before colons **bold** (e.g., **Статус Invoices:**, **Item Master:**, **Цель:**) - these are important category markers for training
- Use `**bold**` not `__bold__`
- Preserve original emphasis from source

### Separators
- Use `------` (6 dashes) as section separator
- Add separator after:
  - Header section (after Passcode)
  - Agenda/Questions section
  - Meeting Report Header section
  - Between individual topics

---

## WHAT TO PRESERVE (EVERYTHING)

✅ **Every discussion point - verbatim**  
✅ **Every decision - exact wording**  
✅ **Every action item - complete description**  
✅ **Every technical detail**  
✅ **Every criticism and rationale**  
✅ **Every business context explanation**  
✅ **Every number, metric, date**  
✅ **Every JIRA ticket and URL**  
✅ **Every blocker and dependency**  
✅ **Every attendee name**  
✅ **⚠️ EVERY TIMESTAMP from video recordings** - (HH:MM), (MM:SS - MM:SS), etc.  
✅ **All code/technical terms**  
✅ **All quotes from participants**

---

## RESTRUCTURING PROCESS

### Step 1: Identify Components
Scan the original file and identify:
- Recording link and passcode
- Agenda items (usually at top)
- Topic discussions
- Action items
- Links and tickets

### Step 2: Create Header
Build consistent header with recording link at top

### Step 3: Format Agenda
If agenda exists (even without "Agenda" heading), structure it consistently

### Step 4: Add "Темы обсуждения" Section Header
Before topics, add:
```markdown
## Темы обсуждения

------
```

### Step 5: Restructure Each Topic
For each topic:
1. Extract all information about that topic
2. If topic uses table format for parameters - convert to field format
3. Organize into standard sections (Контекст, Ключевые моменты, etc.)
4. **Copy exact text** - do not rephrase
5. Preserve all details including inline timestamps
6. Add `------` separator after each topic

### Step 6: Verify Completeness
Check that EVERY piece of information from original is in the new format

### Step 7: Verify Formatting
Check all separators `------` are in place:
- After header
- After Agenda/Questions
- After Meeting Report Header
- Between topics

---

## EXAMPLES

### BEFORE (Unstructured)
```markdown
# Product Review 3 Nov

https://route4me.zoom.us/rec/share/NT0x8...
Код доступа: PF41yd#X
- Location Snapshot [[Alexey Gusentsov](mailto:alexey.gusentsov@route4me.com)]
  - Tab: Service Time
- Strategic Optimizations
  - Scatter Plot [[Manar Kurmanov](mailto:manar.kurmanov@route4me.com)]
```

### AFTER (Structured)
```markdown
# Product Review 03 Nov 2025

**Recording:** https://route4me.zoom.us/rec/share/NT0x8...  
**Passcode:** PF41yd#X

## Agenda

- **Location Snapshot** - Owner: Alexey Gusentsov (alexey.gusentsov@route4me.com)
  - Tab: Service Time
  
- **Strategic Optimizations** - Owner: Manar Kurmanov (manar.kurmanov@route4me.com)
  - Scatter Plot
```

---

### BEFORE (Missing Structure in Topic)
```markdown
Facility assignment is broken for Matthew's. Dan said it's critical. 
Need to fix fallback logic. Artur will do it.
```

### AFTER (Structured, All Content Preserved)
```markdown
### 1. Facility Assignment Issue for Matthew's Client

**Ответственный:** Artur Moskalenko  
**Priority:** Critical

#### Контекст / Цель
Facility assignment is broken for Matthew's client.

#### Ключевые тезисы, директивы и мнения Дэна
- Dan said this issue is critical and must be addressed immediately.

#### Решения и План Действий
- **Artur Moskalenko**: Fix fallback logic for facility assignment
```

---

### Example: Label Formatting in "Ключевые моменты обсуждения и предложения команды"

**BEFORE (without bold labels):**
```markdown
#### Ключевые моменты обсуждения и предложения команды
1. Статус Invoices: Показана таблица с Invoices, где статусы (например, Paid) берутся из внешней системы, а Pending генерируется внутренне (2:33:52).
2. Item Master (Товары): Нужен полноценный вид для Item Master (товаров), где будут видны все атрибуты, включая различные типы идентификаторов (UPC, ISBN) и их историю (2:55:00).
3. Цель: Создать авторитетный автоматический черновик того, что произошло в поле (3:09:43).
```

**AFTER (with bold labels for training):**
```markdown
#### Ключевые моменты обсуждения и предложения команды
1. **Статус Invoices:** Показана таблица с Invoices, где статусы (например, Paid) берутся из внешней системы, а Pending генерируется внутренне (2:33:52).
2. **Item Master (Товары):** Нужен полноценный вид для Item Master (товаров), где будут видны все атрибуты, включая различные типы идентификаторов (UPC, ISBN) и их историю (2:55:00).
3. **Цель:** Создать авторитетный автоматический черновик того, что произошло в поле (3:09:43).
```

---

## QUALITY CHECKLIST

Before marking restructuring as complete:

- [ ] Recording link at top
- [ ] Passcode included (if exists)
- [ ] Agenda formatted consistently (if exists)
- [ ] Every topic has standard section structure
- [ ] ALL original content is preserved
- [ ] All links preserved and properly formatted
- [ ] All names preserved with emails where available
- [ ] All timestamps from video recordings preserved (critical!)
- [ ] All JIRA tickets preserved
- [ ] All action items have responsible person
- [ ] Original language preserved
- [ ] No information lost or condensed
- [ ] Clean markdown formatting
- [ ] Section separators `------` in place (after header, after agenda, after report header, between topics)
- [ ] Double brackets `[[Name]]` converted to single `[Name]`
- [ ] "## Темы обсуждения" section added before topics
- [ ] Table format converted to field format (if applicable)
- [ ] Inline timestamps preserved within text (e.g., "(11:34)")
- [ ] Labels before colons in "Ключевые моменты обсуждения и предложения команды" section are **bold** (e.g., **Статус Invoices:**, **Цель:**) for training purposes
- [ ] Inline numbered lists (e.g., "1) xxx 2) yyy") converted to proper markdown numbered list format
- [ ] CEO name corrected: "Dan"/"Dan's" in English context (never "Den" in English), "Дэн" acceptable in Russian context

---

## VERSION
**Version:** 2.1  
**Last Updated:** November 14, 2025  
**Changes in v2.1:**
- Added rule for converting inline numbered lists to proper markdown format
- Added critical rule for CEO name: always "Dan"/"Dan's" in English (never "Den"), "Дэн" acceptable in Russian context

**Purpose:** RESTRUCTURE (not reduce) Product Review transcripts into consistent format while preserving EVERY detail

