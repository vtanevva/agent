#!/bin/bash
# Quick test script for User Awareness memory system

set -e

BASE_URL="http://localhost:10000"
USER_ID="test-user-$(date +%s)"
THREAD_ID="test-thread-001"

echo "=========================================="
echo "User Awareness Memory System Test"
echo "=========================================="
echo ""
echo "User ID: $USER_ID"
echo "Thread ID: $THREAD_ID"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test 1: Health Check
echo -e "${BLUE}Test 1: Health Check${NC}"
curl -s "$BASE_URL/memory/health" | jq .
echo ""

# Test 2: Ingest a message
echo -e "${BLUE}Test 2: Ingest Message${NC}"
curl -s -X POST "$BASE_URL/memory/ingest-message" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"thread_id\": \"$THREAD_ID\",
    \"channel\": \"test\",
    \"direction\": \"in\",
    \"text\": \"I prefer morning meetings and I work as a software engineer at TechCorp. I like async communication.\"
  }" | jq .
echo ""

# Test 3: Create a test document
echo -e "${BLUE}Test 3: Create Test Document${NC}"
cat > /tmp/test_doc.txt << 'EOF'
Project Requirements Document

Overview:
This project aims to build an AI assistant with the following features:
- Natural language understanding
- Context awareness from past conversations
- Integration with email and calendar systems
- Document upload and semantic search (RAG)

Technical Stack:
- Backend: Python with Flask
- Database: MongoDB for structured data
- Vector Database: Pinecone for embeddings
- LLM: OpenAI GPT-4

The assistant should remember user preferences and provide personalized responses based on conversation history and uploaded documents.
EOF

echo "Created test document: /tmp/test_doc.txt"
echo ""

# Test 4: Upload document
echo -e "${BLUE}Test 4: Upload Document${NC}"
curl -s -X POST "$BASE_URL/memory/upload-file" \
  -F "file=@/tmp/test_doc.txt" \
  -F "user_id=$USER_ID" \
  -F "title=Project Requirements" | jq .
echo ""

# Wait for background processing
echo -e "${BLUE}Waiting 5 seconds for background processing...${NC}"
sleep 5
echo ""

# Test 5: List facts
echo -e "${BLUE}Test 5: List Extracted Facts${NC}"
curl -s "$BASE_URL/memory/facts?user_id=$USER_ID" | jq .
echo ""

# Test 6: Retrieve context
echo -e "${BLUE}Test 6: Retrieve Context (Query: 'project requirements')${NC}"
curl -s "$BASE_URL/memory/context?user_id=$USER_ID&q=project+requirements" | jq .
echo ""

# Test 7: Add more messages for thread summary
echo -e "${BLUE}Test 7: Add Multiple Messages (for thread summary)${NC}"
for i in {1..6}; do
  curl -s -X POST "$BASE_URL/memory/ingest-message" \
    -H "Content-Type: application/json" \
    -d "{
      \"user_id\": \"$USER_ID\",
      \"thread_id\": \"$THREAD_ID\",
      \"channel\": \"test\",
      \"direction\": \"in\",
      \"text\": \"Message $i: Discussing the project requirements and timeline.\"
    }" > /dev/null
  echo "Sent message $i"
done
echo ""

# Wait for summary generation
echo -e "${BLUE}Waiting 5 seconds for summary generation...${NC}"
sleep 5
echo ""

# Test 8: Get thread summary
echo -e "${BLUE}Test 8: Get Thread Summary${NC}"
curl -s "$BASE_URL/memory/threads/$THREAD_ID/summary?user_id=$USER_ID" | jq .
echo ""

# Test 9: Search facts by query
echo -e "${BLUE}Test 9: Search Facts (Query: 'meetings')${NC}"
curl -s "$BASE_URL/memory/facts?user_id=$USER_ID&q=meetings" | jq .
echo ""

# Test 10: Add fact manually
echo -e "${BLUE}Test 10: Add Fact Manually${NC}"
curl -s -X POST "$BASE_URL/memory/facts" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"text\": \"User prefers written documentation over verbal explanations\",
    \"type\": \"preference\",
    \"confidence\": 0.85
  }" | jq .
echo ""

# Final context check
echo -e "${BLUE}Test 11: Final Context Check${NC}"
curl -s "$BASE_URL/memory/context?user_id=$USER_ID&thread_id=$THREAD_ID&q=preferences" | jq '.stats'
echo ""

echo -e "${GREEN}=========================================="
echo "All tests completed!"
echo "==========================================${NC}"
echo ""
echo "Summary:"
echo "- User ID: $USER_ID"
echo "- Thread ID: $THREAD_ID"
echo ""
echo "You can now:"
echo "1. View facts: curl \"$BASE_URL/memory/facts?user_id=$USER_ID\" | jq ."
echo "2. View context: curl \"$BASE_URL/memory/context?user_id=$USER_ID&q=test\" | jq ."
echo "3. View summary: curl \"$BASE_URL/memory/threads/$THREAD_ID/summary?user_id=$USER_ID\" | jq ."
echo ""

