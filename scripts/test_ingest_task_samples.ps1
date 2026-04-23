# Exercise POST /ingest/gmail and POST /ingest/slack against a running core API.
# Prereq: python server.py core  (default http://localhost:5000)
#
#   pwsh -File scripts/test_ingest_task_samples.ps1
#   $env:CORE_BASE='http://127.0.0.1:5000'; pwsh -File scripts/test_ingest_task_samples.ps1

param(
    [string]$CoreBase = $(if ($env:CORE_BASE) { $env:CORE_BASE } else { "http://localhost:5000" })
)

$ErrorActionPreference = "Stop"
$CoreBase = $CoreBase.TrimEnd("/")

function Invoke-Ingest($path, $label, $bodyObj) {
    $uri = "$CoreBase/$path"
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    Write-Host "POST $uri"
    try {
        $r = Invoke-RestMethod -Uri $uri -Method Post -ContentType "application/json" -Body ($bodyObj | ConvertTo-Json -Depth 12)
        $status = $r.status
        $task = $r.grafik_task_id
        $linked = $r.linked_grafik_task_id
        $reason = $r.reason
        $suppress = $r.classification.suppress_task_reason
        Write-Host "status=$status grafik_task_id=$task linked_grafik_task_id=$linked reason=$reason suppress_task_reason=$suppress"
        if ($r.classification) {
            Write-Host "has_action=$($r.classification.has_action) title=$($r.classification.title)"
        }
    }
    catch {
        Write-Host "Request failed: $_" -ForegroundColor Red
    }
}

$mid = [guid]::NewGuid().ToString("n")

# 1) Synthetic app-chat style (gmail_chat) — should NOT create tasks after backend fix
Invoke-Ingest "ingest/gmail" "gmail_chat: show past emails (should log, no task)" @{
    source            = "gmail_chat"
    workspace_id      = "demo-user"
    message_id        = "chat-$mid"
    thread_id         = "session-demo"
    from              = ""
    to                = ""
    subject           = ""
    text              = "Can you show me my past emails from last week?"
    timestamp         = ""
}

# 2) Real-style gmail with bulk precedence (should suppress task if classifier said action)
Invoke-Ingest "ingest/gmail" "gmail + Precedence:bulk newsletter" @{
    source            = "gmail"
    workspace_id      = "demo@example.com"
    message_id        = "msg-$mid-bulk"
    thread_id         = "thr-$mid-bulk"
    from              = "Shop <shop@brand.example>"
    to                = "demo@example.com"
    subject           = "Flash sale: 40% off today"
    body              = "Big savings! Unsubscribe: https://brand.example/u"
    timestamp         = "1710000000000"
    headers           = @(
        @{ name = "Precedence"; value = "bulk" }
    )
}

# 3) Human request (likely actionable — may create/link task depending on GRAFIK list mapping)
Invoke-Ingest "ingest/gmail" "gmail: colleague asks for doc" @{
    source            = "gmail"
    workspace_id      = "demo@example.com"
    message_id        = "msg-$mid-work"
    thread_id         = "thr-$mid-work"
    from              = "Alex <alex@client.example>"
    to                = "demo@example.com"
    subject           = "Need the Q1 deck by Friday 5pm"
    body              = "Hi — can you send the final Q1 presentation deck by Friday 5pm? Thanks."
    timestamp         = "1710000001000"
}

# 4) Slack-style message
Invoke-Ingest "ingest/slack" "slack: channel ping" @{
    workspace_id = "T000000"
    channel      = "C-general"
    ts           = "1710000002.000000"
    user_id      = "U000001"
    text         = "Please review the security PR today — blocking release."
}

# 5) slack_chat delegate (should not task)
Invoke-Ingest "ingest/slack" "slack_chat (synthetic; should log, no task)" @{
    source       = "slack_chat"
    workspace_id = "demo-user"
    channel      = "web_chat:session-1"
    ts           = "1710000003.000001"
    user_id      = "demo-user"
    text         = "Summarize what I missed in Slack yesterday"
}

Write-Host "`nDone. Interpretation: gmail_chat/slack_chat should omit grafik_task_id; bulk marketing should omit task when suppressed." -ForegroundColor Green
