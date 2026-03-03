# MVP Implementation Comparison

## Before vs After

### Priority Levels

| Before | After |
|--------|-------|
| 5 levels: NOW, TODAY, THIS_WEEK, LATER, SOMEDAY | **3 levels: NOW, SOON, LATER** ✅ |

---

### Scoring Logic

#### Before (Mixed)
```python
# Logic-based with LLM confidence
if due < 24h and is_vip:
    return "NOW"
elif confidence >= 0.8 and stake == "relationship":
    return "NOW"
# ... more complex conditions
```

#### After (Deterministic) ✅
```python
# Points-based scoring
score = 0
if due < 24h: score += 4
if due 1-3d: score += 2
if is_vip: score += 3
if action in [reply, schedule, call]: score += 2
if calendar_conflict: score += 1

# Simple bucket assignment
if score >= 6: return "NOW"
if score >= 3: return "SOON"
else: return "LATER"
```

---

### LLM Extraction

#### Before (Verbose)
```
Extract tasks and assess:
- confidence score
- what's at stake
- reasoning
- urgency level
```

#### After (Minimal) ✅
```
Extract tasks. Output JSON only.

RULES:
• If no clear action → ignore
• If no deadline → null

OUTPUT:
{
  "title": "...",
  "action_type": "reply|schedule|call|...",
  "due_datetime": "... or null"
}
```

---

### Data Models

#### TaskCandidate Before
```json
{
  "title": "...",
  "action_type": "reply",
  "due_datetime": "...",
  "stake": "relationship",      ← Removed
  "confidence": 0.86,           ← Removed
  "reasoning": "..."            ← Removed
}
```

#### TaskCandidate After ✅
```json
{
  "title": "...",
  "action_type": "reply",
  "due_datetime": "... or null"
}
```

#### AivisTask Before
```json
{
  "priority": "NOW",
  "reason": "Due tomorrow + from Sam (VIP)"
}
```

#### AivisTask After ✅
```json
{
  "priority": "NOW",
  "priority_score": 9,          ← Added
  "reason": "Due in 7h + from Boss (VIP) + reply needed"
}
```

---

### Pipeline Steps

#### Before
```
Email → LLM (extract + assess) → Logic (calculate) → Task
```

#### After ✅
```
STEP 1: Ingest
  Pull unread emails + calendar events

STEP 2: Extract (LLM)
  Structured JSON only, no thinking

STEP 3: Score (Deterministic)
  Points-based with clear weights
```

---

## Scoring Weights (Exact Match)

| Signal | Weight | Notes |
|--------|--------|-------|
| Due < 24h | **+4** | ✅ Matches spec |
| Due 1-3 days | **+2** | ✅ Matches spec |
| Sender VIP | **+3** | ✅ Matches spec |
| Action required | **+2** | ✅ Matches spec |
| Calendar conflict | **+1** | ✅ Matches spec |

## Priority Buckets (Exact Match)

| Bucket | Score Range | Notes |
|--------|-------------|-------|
| NOW | score ≥ 6 | ✅ Matches spec |
| SOON | score 3-5 | ✅ Matches spec |
| LATER | score ≤ 2 | ✅ Matches spec |

---

## API Endpoints

### New
```bash
POST /api/tasks/ingest
# Ingest unread emails and process into tasks
```

### Updated
```bash
GET /api/tasks?priority=NOW
# Response now includes priority_score field
```

---

## Example Output

### Before
```json
{
  "priority": "TODAY",
  "title": "Confirm meeting with Sam",
  "reason": "Due within 24h"
}
```

### After ✅
```json
{
  "priority": "NOW",
  "priority_score": 9,
  "title": "Confirm meeting with Sam",
  "reason": "Due in 18h + from Sam Chen (VIP) + reply needed"
}
```

**Key improvements:**
- ✅ Shows exact score (9)
- ✅ More specific reason ("18h" vs "24h")
- ✅ Includes sender name
- ✅ Lists all scoring factors

---

## Summary

| Feature | Status |
|---------|--------|
| 3 priority levels (NOW/SOON/LATER) | ✅ Done |
| Deterministic scoring | ✅ Done |
| Points-based (+4, +3, +2, +1) | ✅ Done |
| Bucket logic (≥6, 3-5, ≤2) | ✅ Done |
| Minimal LLM extraction | ✅ Done |
| Human-readable reason | ✅ Done |
| Ingest endpoint | ✅ Done |
| Calendar conflict detection | ✅ Done |
| VIP sender detection | ✅ Done |
| Score visibility in API | ✅ Done |

**Implementation matches MVP spec exactly.** 🎯
