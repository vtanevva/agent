# Codebase Cleanup Analysis - Unnecessary Parts

## Summary
This document identifies parts of the codebase that are not needed and can be safely removed or simplified.

---

## 🔴 HIGH PRIORITY - Remove These

### 1. **Unused Feature Flags**
**Location:** `app/config.py` lines 109-110

**Issue:** `ENABLE_RAG` and `ENABLE_AUTOGEN` are defined but **never checked anywhere** in the codebase.

**Recommendation:** 
- Remove `ENABLE_AUTOGEN` (completely unused)
- Remove `ENABLE_RAG` (RAG is always enabled via memory system, no flag needed)
- Keep `ENABLE_MEMORY` (actually used)

**Files to update:**
- `app/config.py`
- `env.example`
- `docs/DEPLOYMENT_GUIDE.md`

---

### 2. **Unused LLM Provider Support**
**Location:** `app/config.py` line 43

**Issue:** `LLM_PROVIDER` supports "anthropic" and "azure" but the code **only uses OpenAI**. The `LLMService` class hardcodes OpenAI.

**Recommendation:**
- Remove `LLM_PROVIDER` config option (or implement it properly)
- Simplify config to only support OpenAI for now
- If multi-provider is needed later, implement it properly

**Files to update:**
- `app/config.py` (remove or implement)
- `app/services/llm_service.py` (currently only OpenAI)

---

### 3. **Stub NodesService**
**Location:** `app/services/nodes_service.py`

**Issue:** This is a **complete stub** that does nothing. It's passed to agents but never actually used.

**Recommendation:**
- **Option A:** Remove entirely (simplest)
  - Remove `app/services/nodes_service.py`
  - Remove from `app/agents/orchestrator.py` (line 307, 316, 322)
  - Remove from `app/agents/aivis_core_agent.py` (lines 22, 32, 37)
  
- **Option B:** Keep as placeholder if planning to implement soon
  - Add TODO comment with implementation plan
  - Document why it exists

**Impact:** No functional impact - it's already a stub.

---

### 4. **Commented-Out Dead Code**
**Location:** Multiple files

**Issues:**
- `app/api/chat_routes.py` lines 54-60: Commented contact note extraction
- `app/api/chat_routes.py` lines 354-370: Commented old fact extraction
- `app/api/chat_routes.py` lines 63-150: `_extract_contact_notes()` function (never called)

**Recommendation:** Remove all commented-out code blocks. If needed later, it's in git history.

**Files to clean:**
- `app/api/chat_routes.py` (remove `_extract_contact_notes` function entirely)
- Remove commented blocks

---

### 5. **Unused LLMService Methods**
**Location:** `app/services/llm_service.py`

**Issue:** 
- `extract_facts()` method (line 234) - **Never used** (replaced by MemoryGate)
- `summarize_facts()` method (line 270) - **Never used** (replaced by MemoryGate)

**Recommendation:** Remove these methods. The new memory system uses `MemoryGate` instead.

---

### 6. **Duplicate Test File**
**Location:** Root directory vs `tests/` directory

**Issue:** `test_gmail_connection.py` exists in root but there's also `tests/test_gmail_connection.py`

**Recommendation:** 
- Keep only `tests/test_gmail_connection.py`
- Remove root-level `test_gmail_connection.py`

---

### 7. **Unused Instagram/Facebook OAuth**
**Location:** `env.example`, `app/utils/oauth_utils.py`

**Issue:** Instagram OAuth config exists but **no actual implementation** found.

**Recommendation:**
- Remove from `env.example` (lines 54-57)
- Check `app/utils/oauth_utils.py` - if only commented code, remove it
- Keep if planning to implement soon (add TODO)

---

## 🟡 MEDIUM PRIORITY - Consider Removing

### 8. **Tool Registry Stub**
**Location:** `app/utils/tool_registry.py`

**Issue:** This is a stub that does nothing. The comment says "agents call functions directly now".

**Status:** ✅ **KEEP** - Actually imported by 6 tool files:
- `app/tools/email/extract_todos.py`
- `app/tools/email/send.py`
- `app/tools/email/style.py`
- `app/tools/email/forward.py`
- `app/tools/email/list.py`
- `app/tools/email/reply.py`

**Recommendation:**
- Keep for backward compatibility (tools import it)
- Consider removing imports from tools if they're not needed
- Or refactor tools to not need it

---

### 9. **Unused Test Files in Root**
**Location:** Root directory

**Files:**
- `test_classification.py`
- `test_triaged_inbox.py` 
- `test_memory_manual.py`
- `test_simple.ps1`

**Recommendation:**
- Move to `tests/` directory for organization
- Or remove if they're outdated/duplicate

---

### 10. **Utility Scripts in Root**
**Location:** Root directory

**Files:**
- `check_user_structure.py`
- `list_collections_and_namespaces.py`
- `delete_waitlist_users.py`

**Recommendation:**
- Move to `scripts/` directory for better organization
- These are useful but should be organized

---

## 🟢 LOW PRIORITY - Keep But Document

### 11. **PINECONE_ENV Config**
**Location:** `app/config.py` line 65

**Issue:** `PINECONE_ENV` is set but Pinecone API no longer uses environment parameter (uses region in index name).

**Recommendation:** 
- Check if actually used
- If not, remove or mark as deprecated
- Update docs if removed

---

### 12. **Multiple Backfill Scripts**
**Location:** `scripts/` directory

**Files:**
- `backfill_email_facts.py`
- `backfill_all_email_facts.py`
- `backfill_facts.py`

**Issue:** Three different backfill scripts with overlapping functionality.

**Recommendation:**
- Consolidate into one script with options
- Or clearly document when to use each
- Keep if they serve different purposes

---

## 📊 Estimated Impact

### Code Reduction:
- **~200-300 lines** of dead/commented code
- **~50-100 lines** of unused config/stubs
- **Total: ~250-400 lines** can be removed

### Files to Delete:
1. `app/services/nodes_service.py` (if removing stub)
2. Root-level `test_gmail_connection.py` (duplicate)
3. Possibly `app/utils/tool_registry.py` (if unused)

### Files to Clean:
1. `app/config.py` (remove unused flags)
2. `app/api/chat_routes.py` (remove commented code)
3. `app/services/llm_service.py` (remove unused methods)
4. `env.example` (remove unused configs)

---

## ✅ Safe to Remove Checklist

- [ ] Remove `ENABLE_AUTOGEN` flag (unused)
- [ ] Remove `ENABLE_RAG` flag (unused)  
- [ ] Remove `LLM_PROVIDER` multi-provider support (unused)
- [ ] Remove `NodesService` stub (unused)
- [ ] Remove `_extract_contact_notes()` function (unused)
- [ ] Remove commented-out code blocks
- [ ] Remove `extract_facts()` and `summarize_facts()` from LLMService (unused)
- [ ] Remove duplicate `test_gmail_connection.py` from root
- [ ] Remove Instagram OAuth config (unused)
- [ ] Move utility scripts to `scripts/` directory
- [ ] Move test files to `tests/` directory

---

## 🚀 Implementation Order

1. **Phase 1 (Safe, No Impact):**
   - Remove unused feature flags
   - Remove commented code
   - Remove duplicate test file

2. **Phase 2 (Verify First):**
   - Check if tool_registry is imported anywhere
   - Verify Instagram OAuth is not used
   - Remove NodesService stub

3. **Phase 3 (Organize):**
   - Move scripts to proper directories
   - Consolidate backfill scripts (optional)

---

## Notes

- All removals are **safe** - these are unused/dead code
- No functional impact expected
- Code will be cleaner and easier to maintain
- Git history preserves everything if needed later

