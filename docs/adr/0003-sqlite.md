# SQLite as primary database

SQLite was chosen over PostgreSQL because WodPlanner runs as a single-process app on a single node with two users. It needs no network database server, no connection pooling, and no separate infrastructure to operate.

WAL mode + `busy_timeout` make it safe under the brief write contention that occurs during periodic background sync. The Online Backup API (`backup-db` CLI) makes safe live backups without rsync.

**Consequence:** SQLite does not work safely on NFS or `ReadWriteMany` volumes. A multi-pod Kubernetes deployment requires a `ReadWriteOnce` PVC (same node) or a migration to PostgreSQL. See `docs/database.md` for the full K8s compatibility matrix.
