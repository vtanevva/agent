# User Awareness System Deployment Checklist

Use this checklist when deploying the User Awareness memory system to production.

## Pre-Deployment

### Environment Setup

- [ ] Set all required environment variables in production
  - [ ] `OPENAI_API_KEY`
  - [ ] `MONGO_URI`
  - [ ] `PINECONE_API_KEY`
  - [ ] `PINECONE_INDEX_NAME`
  - [ ] `PINECONE_ENV`
  - [ ] `EMBEDDING_MODEL`
  - [ ] `UPLOAD_FOLDER`
  - [ ] `FLASK_SECRET_KEY` (strong random value)
  - [ ] `APP_ENV=production`

- [ ] Verify MongoDB connection
  - [ ] Test connection string
  - [ ] Check authentication
  - [ ] Verify database name

- [ ] Verify Pinecone setup
  - [ ] Create production index (separate from dev)
  - [ ] Set correct dimension (1536 for ada-002)
  - [ ] Choose appropriate region
  - [ ] Verify API key permissions

### Dependencies

- [ ] Install all requirements: `pip install -r requirements.txt`
- [ ] Install document parsers:
  - [ ] `PyPDF2` for PDF support
  - [ ] `python-docx` for DOCX support
- [ ] Verify Python version (3.10+)

### Database Setup

- [ ] Run setup script: `python scripts/setup_memory_system.py`
- [ ] Verify indexes created:
  - [ ] `messages` collection indexes
  - [ ] `memory_facts` collection indexes
  - [ ] `thread_summaries` collection indexes
  - [ ] `documents` collection indexes
  - [ ] `document_chunks` collection indexes

### File System

- [ ] Create upload folder: `mkdir -p uploads`
- [ ] Set appropriate permissions (readable/writable by app)
- [ ] Configure file size limits
- [ ] Set up cleanup policy for old uploads

## Testing

### Unit Tests

- [ ] Run all tests: `pytest tests/test_memory_system.py -v`
- [ ] Verify all tests pass
- [ ] Check test coverage

### Integration Tests

- [ ] Test message ingestion
  - [ ] Send test message
  - [ ] Verify stored in MongoDB
  - [ ] Verify embedded in Pinecone
  - [ ] Check fact extraction

- [ ] Test document upload
  - [ ] Upload TXT file
  - [ ] Upload PDF file
  - [ ] Upload DOCX file
  - [ ] Verify chunking
  - [ ] Verify embedding

- [ ] Test context retrieval
  - [ ] Query with user_id
  - [ ] Verify facts returned
  - [ ] Verify doc chunks returned
  - [ ] Check recent messages

- [ ] Test thread summarization
  - [ ] Send 5+ messages
  - [ ] Wait for background processing
  - [ ] Verify summary generated

### API Endpoint Tests

- [ ] `POST /memory/ingest-message` - Returns 200
- [ ] `POST /memory/upload-file` - Returns 200
- [ ] `GET /memory/context` - Returns context bundle
- [ ] `GET /memory/facts` - Returns facts list
- [ ] `POST /memory/facts` - Creates fact
- [ ] `DELETE /memory/facts/<id>` - Deletes fact
- [ ] `GET /memory/threads/<id>/summary` - Returns summary
- [ ] `GET /memory/health` - Returns healthy status

### Security Tests

- [ ] Test user isolation
  - [ ] User A cannot access User B's facts
  - [ ] User A cannot access User B's documents
  - [ ] Pinecone namespaces are separate

- [ ] Test input validation
  - [ ] Missing user_id returns 400
  - [ ] Invalid file type rejected
  - [ ] Large files handled gracefully

- [ ] Test authentication (if implemented)
  - [ ] Unauthorized requests rejected
  - [ ] API keys validated

## Performance

### Load Testing

- [ ] Test concurrent message ingestion
  - [ ] 10 messages/second
  - [ ] 100 messages/second
  - [ ] Monitor queue depth

- [ ] Test concurrent document uploads
  - [ ] Multiple users uploading simultaneously
  - [ ] Large documents (10MB+)
  - [ ] Monitor processing time

- [ ] Test context retrieval latency
  - [ ] Measure P50, P95, P99
  - [ ] Target: <500ms for context retrieval
  - [ ] Monitor vector search performance

### Token Usage

- [ ] Measure average context bundle size
  - [ ] Target: <2000 tokens
  - [ ] Adjust retrieval limits if needed

- [ ] Estimate monthly costs
  - [ ] Embeddings: messages + documents
  - [ ] LLM: context-aware responses
  - [ ] Pinecone: storage + queries

### Background Jobs

- [ ] Verify background queue is working
  - [ ] Fact extraction completes
  - [ ] Thread summarization completes
  - [ ] Document indexing completes

- [ ] Monitor queue depth
  - [ ] Set up alerts for long queues
  - [ ] Consider scaling workers

## Monitoring

### Logging

- [ ] Configure log level (INFO for production)
- [ ] Set up log aggregation (e.g., CloudWatch, Datadog)
- [ ] Monitor for errors:
  - [ ] Fact extraction failures
  - [ ] Vector search errors
  - [ ] MongoDB connection issues
  - [ ] Pinecone API errors

### Metrics

- [ ] Set up metrics collection
  - [ ] Message ingestion rate
  - [ ] Document upload rate
  - [ ] Context retrieval latency
  - [ ] Fact extraction success rate
  - [ ] Background job queue depth

- [ ] Set up dashboards
  - [ ] API endpoint latencies
  - [ ] Error rates
  - [ ] Token usage
  - [ ] Storage growth

### Alerts

- [ ] Configure alerts for:
  - [ ] High error rate (>5%)
  - [ ] High latency (>1s)
  - [ ] Database connection failures
  - [ ] Pinecone API errors
  - [ ] Background queue backup (>100 jobs)
  - [ ] High token usage (cost control)

## Production Readiness

### Code Quality

- [ ] All linter errors fixed
- [ ] No hardcoded secrets
- [ ] Error handling in place
- [ ] Logging statements added
- [ ] Comments and docstrings complete

### Documentation

- [ ] README updated
- [ ] API documentation complete
- [ ] Deployment guide written
- [ ] Runbook for common issues
- [ ] Architecture diagram included

### Backup & Recovery

- [ ] MongoDB backup strategy
  - [ ] Automated daily backups
  - [ ] Test restore procedure

- [ ] Pinecone backup strategy
  - [ ] Export vectors periodically
  - [ ] Test restore procedure

- [ ] Document backup strategy
  - [ ] Uploaded files backed up
  - [ ] Retention policy defined

### Scaling

- [ ] Replace thread-based jobs with Celery/RQ
  - [ ] Set up Redis/RabbitMQ
  - [ ] Configure workers
  - [ ] Test job distribution

- [ ] Consider caching
  - [ ] Redis for frequently accessed facts
  - [ ] Cache thread summaries
  - [ ] Cache context bundles

- [ ] Database optimization
  - [ ] Review index usage
  - [ ] Optimize slow queries
  - [ ] Consider read replicas

## Post-Deployment

### Smoke Tests

- [ ] Test all endpoints in production
- [ ] Upload a real document
- [ ] Send real messages
- [ ] Verify context retrieval

### Monitoring

- [ ] Check logs for errors
- [ ] Verify metrics are being collected
- [ ] Test alerts are working
- [ ] Monitor resource usage

### User Acceptance

- [ ] Test with real users
- [ ] Gather feedback on fact extraction quality
- [ ] Verify response personalization
- [ ] Check document search relevance

### Optimization

- [ ] Review token usage
  - [ ] Adjust retrieval limits if needed
  - [ ] Optimize chunk sizes

- [ ] Review performance
  - [ ] Identify slow queries
  - [ ] Optimize vector search
  - [ ] Tune background job workers

- [ ] Review costs
  - [ ] OpenAI API usage
  - [ ] Pinecone costs
  - [ ] MongoDB storage

## Rollback Plan

In case of issues:

1. **Disable memory system**:
   - [ ] Set `ENABLE_MEMORY=false`
   - [ ] Restart server
   - [ ] App continues without memory features

2. **Revert code**:
   - [ ] Git revert to previous version
   - [ ] Redeploy

3. **Database rollback**:
   - [ ] Restore MongoDB from backup
   - [ ] Restore Pinecone from backup

4. **Communication**:
   - [ ] Notify users of issues
   - [ ] Provide ETA for fix
   - [ ] Update status page

## Production Checklist Summary

### Critical (Must Have)

- ✅ All environment variables set
- ✅ MongoDB connected and indexed
- ✅ Pinecone initialized
- ✅ All tests passing
- ✅ Error handling in place
- ✅ Logging configured
- ✅ Backup strategy defined

### Important (Should Have)

- ✅ Monitoring and alerts set up
- ✅ Load testing completed
- ✅ Security tests passed
- ✅ Documentation complete
- ✅ Rollback plan ready

### Nice to Have

- ⚪ Celery/RQ for background jobs
- ⚪ Redis caching
- ⚪ Advanced metrics dashboard
- ⚪ A/B testing framework
- ⚪ User feedback loop

## Sign-Off

- [ ] Development team approves
- [ ] QA team approves
- [ ] Security team approves (if applicable)
- [ ] Product owner approves
- [ ] DevOps team approves

**Deployment Date**: _________________

**Deployed By**: _________________

**Version**: _________________

---

**Notes**:
- Keep this checklist updated as system evolves
- Review after each deployment
- Share lessons learned with team

