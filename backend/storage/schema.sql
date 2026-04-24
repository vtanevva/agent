PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  data_owner_key TEXT NOT NULL DEFAULT '__unscoped__',
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (data_owner_key, name)
);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT,               -- active/on_hold/completed
  priority TEXT,             -- low/medium/high
  deadline TEXT,             -- ISO UTC if known
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_updated_at TEXT,      -- last meaningful context update (Phase 4)
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_client_name
ON projects(client_id, name);

CREATE TABLE IF NOT EXISTS project_context (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL UNIQUE,
  summary TEXT,
  current_status TEXT,
  current_priorities TEXT,
  blockers TEXT,
  next_steps TEXT,
  key_contacts_json TEXT,
  important_links_json TEXT,
  updated_by TEXT,           -- vanesa / system
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS calendar_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT,
  title TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  timezone TEXT,
  source TEXT,               -- google_calendar / reclaim / manual
  data_owner_key TEXT,       -- same partition as clients (email + login); NULL = legacy
  client_id INTEGER,
  project_id INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_start_end
ON calendar_events(start_at, end_at);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  channel TEXT,
  ts TEXT,
  user TEXT,
  text TEXT,
  payload_json TEXT,
  client_id INTEGER,
  project_id INTEGER,
  classification_type TEXT,
  classification_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_source_sourceid
ON messages(source, source_id);

CREATE INDEX IF NOT EXISTS idx_messages_created_at
ON messages(created_at);

CREATE INDEX IF NOT EXISTS idx_messages_client_project
ON messages(client_id, project_id);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  step TEXT NOT NULL,
  status TEXT NOT NULL,
  data_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_source_sourceid
ON events(source, source_id);

CREATE INDEX IF NOT EXISTS idx_events_created_at
ON events(created_at);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  grafik_task_id TEXT NOT NULL,
  client_id INTEGER,
  project_id INTEGER,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  classification_type TEXT NOT NULL,
  classification_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_source_sourceid
ON tasks(source, source_id);

CREATE INDEX IF NOT EXISTS idx_tasks_grafik_task_id
ON tasks(grafik_task_id);

CREATE INDEX IF NOT EXISTS idx_tasks_client_project
ON tasks(client_id, project_id);

CREATE TABLE IF NOT EXISTS follow_ups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,        -- slack/gmail
  source_id TEXT NOT NULL,     -- messages.source_id
  client_id INTEGER,
  project_id INTEGER,
  type TEXT NOT NULL,          -- awaiting_response/promised_action/follow_up
  status TEXT NOT NULL,        -- open/resolved/expired
  due_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_ups_source_sourceid
ON follow_ups(source, source_id);

CREATE INDEX IF NOT EXISTS idx_follow_ups_client_project
ON follow_ups(client_id, project_id);

CREATE INDEX IF NOT EXISTS idx_follow_ups_status_due
ON follow_ups(status, due_at);

CREATE TABLE IF NOT EXISTS metrics_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  has_action INTEGER NOT NULL,
  reply_generated INTEGER NOT NULL,
  reply_mode TEXT,
  follow_up_created INTEGER NOT NULL,
  task_created INTEGER NOT NULL,
  task_linked INTEGER NOT NULL,
  project_memory_updated INTEGER NOT NULL,
  importance_level TEXT,
  importance_score INTEGER,
  has_schedule_signal INTEGER NOT NULL,
  time_pressure_level TEXT,
  duplicate_delivery INTEGER NOT NULL,
  error INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_events_created_at
ON metrics_events(created_at);

CREATE INDEX IF NOT EXISTS idx_metrics_events_source_status
ON metrics_events(source, status);

-- Gmail Pub/Sub watch baseline per mailbox (historyId)
CREATE TABLE IF NOT EXISTS gmail_watch_state (
  email_address TEXT PRIMARY KEY,
  last_history_id INTEGER,
  topic TEXT,
  label_ids_json TEXT,
  watch_expiration TEXT,
  watch_started_at TEXT,
  updated_at TEXT NOT NULL,
  note TEXT
);

-- Threads the user has already replied to (used to hide answered items from the tasks list).
CREATE TABLE IF NOT EXISTS thread_replies (
  source TEXT NOT NULL,           -- 'gmail' / 'slack'
  workspace_id TEXT NOT NULL,     -- mailbox email / slack workspace
  thread_id TEXT NOT NULL,
  answered_at TEXT NOT NULL,      -- ISO-8601 UTC (when the reply was sent)
  sent_message_id TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (source, workspace_id, thread_id)
);

CREATE INDEX IF NOT EXISTS idx_thread_replies_source_workspace
ON thread_replies(source, workspace_id);

-- Maps Expo app login (user_id) to provider identities for ingest stamping (app_user_id on messages).
CREATE TABLE IF NOT EXISTS profile_link (
  user_id TEXT PRIMARY KEY,
  gmail_address TEXT,
  slack_team_id TEXT,
  slack_user_id TEXT,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_link_gmail_lower
ON profile_link(lower(trim(gmail_address)))
WHERE gmail_address IS NOT NULL AND trim(gmail_address) != '';

CREATE INDEX IF NOT EXISTS idx_profile_link_slack_team
ON profile_link(slack_team_id)
WHERE slack_team_id IS NOT NULL AND trim(slack_team_id) != '';