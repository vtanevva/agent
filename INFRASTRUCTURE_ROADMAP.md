# Infrastructure Roadmap: When to Add Redis & Background Jobs

## 🎯 Current State (Good Enough for Now)

✅ **What's Working:**
- Python threading for background tasks (email classification)
- MongoDB for persistent caching
- In-memory rate limiting (works for single server)
- In-memory style cache (works, but lost on restart)

## 📊 Decision Matrix

### Redis Caching - Add When:

| Criteria | Current | Threshold | Status |
|----------|---------|-----------|--------|
| Server count | 1 | 2+ | ⏳ Wait |
| API response time | < 1s | > 2s | ⏳ Wait |
| MongoDB read load | Low | High | ⏳ Wait |
| Cache hit rate needed | N/A | > 80% | ⏳ Wait |

**When to add:** When you scale to 2+ servers OR see performance issues

### Background Job Queue - Add When:

| Criteria | Current | Threshold | Status |
|----------|---------|-----------|--------|
| Background tasks | 1-2 | 3+ | ⏳ Wait |
| Task failures | Rare | Common | ⏳ Wait |
| Need scheduling | No | Yes | ⏳ Wait |
| Need retry logic | No | Yes | ⏳ Wait |
| Task monitoring | Basic | Advanced | ⏳ Wait |

**When to add:** When you add more agents OR need better task management

## 🚦 Recommended Timeline

### Phase 1: Now (Current)
- ✅ Keep using threading for background tasks
- ✅ Keep MongoDB for caching
- ✅ Keep in-memory rate limiting
- ✅ Add monitoring/logging to track when you hit limits

### Phase 2: When Adding More Agents
- ⚠️ If adding 2+ more agents with background tasks → Add Celery/RQ
- ⚠️ If tasks start failing → Add Celery/RQ with retry logic

### Phase 3: When Scaling
- ⚠️ If deploying 2+ servers → Add Redis for distributed rate limiting
- ⚠️ If API becomes slow → Add Redis caching layer

## 💡 Quick Wins (Do These First)

Instead of Redis/Celery, consider these simpler improvements:

### 1. Improve Current Caching
```python
# app/services/cache_service.py (simple file-based cache)
import json
import os
from datetime import datetime, timedelta

CACHE_DIR = "cache"
CACHE_TTL = timedelta(hours=24)

def get_cache(key):
    filepath = f"{CACHE_DIR}/{key}.json"
    if os.path.exists(filepath):
        with open(filepath) as f:
            data = json.load(f)
            if datetime.now() - datetime.fromisoformat(data['timestamp']) < CACHE_TTL:
                return data['value']
    return None

def set_cache(key, value):
    os.makedirs(CACHE_DIR, exist_ok=True)
    filepath = f"{CACHE_DIR}/{key}.json"
    with open(filepath, 'w') as f:
        json.dump({'value': value, 'timestamp': datetime.now().isoformat()}, f)
```

### 2. Better Background Task Management
```python
# app/utils/background_tasks.py
import threading
from queue import Queue
from typing import Callable

task_queue = Queue(maxsize=100)
worker_threads = []

def start_workers(num_workers=2):
    """Start background worker threads"""
    for i in range(num_workers):
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        worker_threads.append(t)

def _worker():
    """Worker thread that processes tasks"""
    while True:
        task, args, kwargs = task_queue.get()
        try:
            task(*args, **kwargs)
        except Exception as e:
            logger.error(f"Background task failed: {e}")
        finally:
            task_queue.task_done()

def enqueue_task(task: Callable, *args, **kwargs):
    """Enqueue a task for background processing"""
    task_queue.put((task, args, kwargs))
```

### 3. Add Task Monitoring
```python
# Track background task status
background_tasks = {}

def track_task(task_id, status, result=None):
    background_tasks[task_id] = {
        'status': status,  # 'pending', 'running', 'completed', 'failed'
        'result': result,
        'timestamp': datetime.now().isoformat()
    }
```

## 🔮 When You're Ready: Implementation Guide

### Redis Caching (Simple Setup)

```python
# requirements.txt
redis>=5.0.0

# app/services/redis_cache.py
import redis
import json
from app.config import Config

redis_client = None

def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True
        )
    return redis_client

def cache_get(key: str, default=None):
    """Get from cache"""
    try:
        value = get_redis().get(key)
        return json.loads(value) if value else default
    except:
        return default

def cache_set(key: str, value, ttl=3600):
    """Set cache with TTL"""
    try:
        get_redis().setex(key, ttl, json.dumps(value))
    except:
        pass
```

### Celery Setup (When Needed)

```python
# requirements.txt
celery>=5.3.0
redis>=5.0.0  # Celery broker

# app/tasks/__init__.py
from celery import Celery
from app.config import Config

celery_app = Celery(
    'tasks',
    broker=f'redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/0',
    backend=f'redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/0'
)

# app/tasks/email_tasks.py
from app.tasks import celery_app

@celery_app.task
def classify_emails_background(user_id: str, max_emails: int = 20):
    """Background task for email classification"""
    from app.services.gmail_service import classify_background
    return classify_background(user_id, max_emails)
```

## 📈 Monitoring Checklist

Before adding Redis/Celery, track these metrics:

- [ ] API response times (should be < 1s)
- [ ] Background task completion rate
- [ ] MongoDB query performance
- [ ] Server memory usage
- [ ] Number of concurrent users
- [ ] Task failure rate

**Add infrastructure when metrics show you need it, not before.**

## 🎯 Bottom Line

**Don't add Redis/Celery yet because:**
1. ✅ Current solution works for single server
2. ✅ You're still building features (add agents first)
3. ✅ No performance issues yet
4. ✅ Adds complexity without clear benefit

**Add Redis/Celery when:**
1. ⚠️ You deploy 2+ servers (need distributed rate limiting)
2. ⚠️ You have 3+ background tasks (need better management)
3. ⚠️ You see performance issues (need caching)
4. ⚠️ Tasks start failing (need retry logic)

**Focus on:**
- ✅ Adding more agents
- ✅ Improving error handling
- ✅ Adding tests
- ✅ Better monitoring/logging

Then add infrastructure when you actually need it! 🚀

