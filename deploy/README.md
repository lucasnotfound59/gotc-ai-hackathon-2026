# Isolated cloud deployment

`deploy.py` creates a local release package by default. It changes the server only
when explicitly run with `--execute`:

```powershell
python deploy/deploy.py
python deploy/deploy.py --execute
```

Commit this project's source first. The script records the Git commit SHA, content
digest, release archive SHA-256, URL and health result in `.runtime/deployment.json`.
Without a project-owned Git repository it records the source content SHA-256.
The release includes public HTML/CSS/JS (including `platform-admin.js`), approved
assets/downloads, backend Python source and `scripts/backup_event.py`. The backup
script is an operator CLI, not an HTTP download. Data, databases, private access
files, tests and QA are excluded.

The deploy tool needs local Paramiko and reuses the existing verified SSH identity
at `~/.ssh/realtalk_ecs` with `~/.ssh/known_hosts` and strict host-key checking.
It never reads the key into logs, shell arguments or the repository.

The new service uses `/opt/gotc-hackathon`, system user/service `gotc-hackathon`,
loopback port 5274, and `https://8.141.114.201/gotc/`. Python 3.12 standard library
is sufficient on the server. Nginx preserves `/gotc` when proxying. The 27 September
event routes and databases are independent and untouched.

Before activation the installer backs up Nginx and any existing GOTC SQLite
database. It verifies the new service locally, tests and reloads Nginx, checks
the public board API, and confirms the original services are active. Failure
restores this service's prior current release/unit and the Nginx edit; data is
preserved. A concurrent Nginx edit is never overwritten automatically.

The initial admin access file is transferred through SFTP to
`.runtime/admin-access.txt`. It is never printed and must never be committed or
shared publicly. Keep `.runtime/` ignored by Git.
