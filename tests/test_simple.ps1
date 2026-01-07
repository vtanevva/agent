# Simple PowerShell test script for memory system
# Run this while server is running

$baseUrl = "http://localhost:10000"
$userId = "test-user-$(Get-Date -Format 'yyyyMMddHHmmss')"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "User Awareness Memory System Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "User ID: $userId" -ForegroundColor Yellow
Write-Host ""

# Test 1: Health Check
Write-Host "[TEST 1] Health Check" -ForegroundColor Green
Write-Host "----------------------------------------"
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/memory/health" -Method Get
    Write-Host "✅ Health check passed!" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "❌ Health check failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 2: Ingest Message
Write-Host "[TEST 2] Ingest Message" -ForegroundColor Green
Write-Host "----------------------------------------"
try {
    $body = @{
        user_id = $userId
        thread_id = "test-thread-001"
        channel = "test"
        direction = "in"
        text = "I prefer morning meetings and I work as a software engineer at TechCorp."
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$baseUrl/memory/ingest-message" -Method Post -Body $body -ContentType "application/json"
    Write-Host "✅ Message ingested!" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "❌ Message ingestion failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 3: Wait and check facts
Write-Host "[TEST 3] Check Facts (waiting 5 seconds for processing...)" -ForegroundColor Green
Write-Host "----------------------------------------"
Start-Sleep -Seconds 5

try {
    $response = Invoke-RestMethod -Uri "$baseUrl/memory/facts?user_id=$userId" -Method Get
    Write-Host "✅ Facts retrieved!" -ForegroundColor Green
    Write-Host "Facts found: $($response.count)" -ForegroundColor Yellow
    
    if ($response.facts) {
        Write-Host "`nExtracted Facts:" -ForegroundColor Cyan
        foreach ($fact in $response.facts) {
            Write-Host "  - $($fact.text)" -ForegroundColor White
            Write-Host "    Type: $($fact.type), Confidence: $($fact.confidence)" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "❌ Facts retrieval failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 4: Add fact manually
Write-Host "[TEST 4] Add Fact Manually" -ForegroundColor Green
Write-Host "----------------------------------------"
try {
    $body = @{
        user_id = $userId
        text = "User prefers async communication"
        type = "preference"
        confidence = 0.9
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$baseUrl/memory/facts" -Method Post -Body $body -ContentType "application/json"
    Write-Host "✅ Fact added manually!" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "❌ Add fact failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 5: Retrieve context
Write-Host "[TEST 5] Retrieve Context" -ForegroundColor Green
Write-Host "----------------------------------------"
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/memory/context?user_id=$userId&q=work" -Method Get
    Write-Host "✅ Context retrieved!" -ForegroundColor Green
    
    if ($response.stats) {
        Write-Host "`nContext Stats:" -ForegroundColor Cyan
        Write-Host "  Facts: $($response.stats.facts_count)" -ForegroundColor White
        Write-Host "  Summaries: $($response.stats.summaries_count)" -ForegroundColor White
        Write-Host "  Doc Chunks: $($response.stats.doc_chunks_count)" -ForegroundColor White
        Write-Host "  Recent Messages: $($response.stats.recent_messages_count)" -ForegroundColor White
    }
    
    if ($response.context.profile_summary) {
        Write-Host "`nProfile Summary:" -ForegroundColor Cyan
        Write-Host "  $($response.context.profile_summary)" -ForegroundColor White
    }
} catch {
    Write-Host "❌ Context retrieval failed: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Tests Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Your test user ID: $userId" -ForegroundColor Yellow
Write-Host "View facts: $baseUrl/memory/facts?user_id=$userId" -ForegroundColor Gray

