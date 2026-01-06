# Re-classify Old Emails with v3.0 + Smart Fact Extraction

## 🎯 Quick Start

### **Option 1: API Endpoint** (Easiest)

```powershell
Invoke-RestMethod -Uri "http://localhost:10000/memory/admin/reclassify-emails" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"user_id": "v", "max_emails": 100}'
```

**Process all emails:**
```powershell
Invoke-RestMethod -Uri "http://localhost:10000/memory/admin/reclassify-emails" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"user_id": "v"}'
```

---

### **Option 2: Python Script** (More Control)

```bash
# Re-classify 100 old emails
python scripts/reclassify_and_extract_facts.py --max-emails 100

# Re-classify ALL old emails
python scripts/reclassify_and_extract_facts.py

# Custom batch size
python scripts/reclassify_and_extract_facts.py --max-emails 200 --batch-size 25
```

---

## 📊 What It Does

```
1. Find old emails (classification v2.0 or earlier)
   ↓
2. Re-classify with v3.0 (10 categories)
   ↓
3. Update database with new category
   ↓
4. IF category is important (urgent, action_items, clients, etc.)
   → Extract facts ✅
   ↓
5. IF category is noise (notifications, promotional, etc.)
   → Skip fact extraction ❌
```

---

## ✅ Categories That Extract Facts

- `urgent` - High priority
- `action_items` - Tasks, meetings
- `clients` - Client communications
- `waiting_for_reply` - Follow-ups
- `normal` - Personal emails

---

## ❌ Categories That Skip Facts

- `notifications` - GitHub, Jira, Slack
- `newsletters` - Newsletters, digests
- `promotional` - Marketing emails
- `transactional` - Orders, shipping
- `social` - LinkedIn, Twitter
- `invoices` - Billing

---

## 📈 Expected Results

**Example for 1000 old emails:**

```
Total processed: 1000
Re-classified: 1000
Facts extracted: 420 (42%)
Skipped (noise): 580 (58%)

Category breakdown:
✅ action_items: 250
✅ urgent: 100
✅ clients: 50
✅ waiting_for_reply: 20
❌ notifications: 300
❌ newsletters: 150
❌ promotional: 80
❌ transactional: 30
❌ social: 20
```

---

## 💰 Cost Savings

**Old system (extract from ALL):**
- 1000 emails × $0.0001 = **$0.10**

**New system (extract from ~40%):**
- 420 emails × $0.0001 = **$0.04**
- **60% cheaper!** 🎯

---

## 🔍 Monitor Progress

**Server logs:**
```
[*] Processing batch 1...
    [OK] Processed 50/100 emails
         Re-classified: 50, Facts extracted: 22, Skipped: 28

[*] Category breakdown:
    ✅ action_items: 15
    ✅ urgent: 7
    ❌ notifications: 20
    ❌ newsletters: 8
```

**Check facts:**
```powershell
Invoke-WebRequest -Uri "http://localhost:10000/memory/facts?user_id=v" | ConvertFrom-Json
```

---

## ⚙️ Options

### **API Endpoint:**
```json
{
  "user_id": "v",        // required
  "max_emails": 100      // optional (default: all)
}
```

### **Python Script:**
```bash
--user-id v            # User ID
--max-emails 100       # Limit (default: all)
--batch-size 50        # Batch size (default: 50)
```

---

## 🚀 Recommended Approach

1. **Test with small batch first:**
   ```bash
   python scripts/reclassify_and_extract_facts.py --max-emails 50
   ```

2. **Check results:**
   ```powershell
   Invoke-WebRequest -Uri "http://localhost:10000/memory/facts?user_id=v"
   ```

3. **If looks good, process all:**
   ```bash
   python scripts/reclassify_and_extract_facts.py
   ```

---

## 📝 Notes

- **Runs in background** - Non-blocking
- **Safe to run multiple times** - Only processes outdated classifications
- **Preserves email content** - Only updates category field
- **Facts deduplicated** - Won't create duplicate facts

---

## ✅ Verification

After running:

```powershell
# 1. Check classification version
# MongoDB: db.emails.findOne({user_id: "v"}).classification_version
# Should show: "3.0"

# 2. Check category distribution
# MongoDB: db.emails.aggregate([
#   {$match: {user_id: "v"}},
#   {$group: {_id: "$category", count: {$sum: 1}}}
# ])

# 3. Check extracted facts
Invoke-WebRequest -Uri "http://localhost:10000/memory/facts?user_id=v" | 
  ConvertFrom-Json | 
  Select-Object -ExpandProperty facts | 
  Where-Object {$_.source_ref -like "email:*"} | 
  Measure-Object

# 4. Test retrieval
# Send message: "When should we schedule a meeting?"
# AI should use facts from emails
```

---

## 🎯 Done!

Your old emails are now:
- ✅ Classified with v3.0 (better categories)
- ✅ Facts extracted from important emails only
- ✅ Noise emails filtered out
- ✅ Cost-optimized

**Next time you chat**, the AI will use facts from your email history! 🧠

