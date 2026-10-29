"""Package the public allowlist; --execute explicitly deploys the isolated service.

The existing SSH key is referenced by path only. Admin access is fetched via SFTP
into the ignored .runtime directory and is never printed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import uuid

PROJECT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = '/opt/gotc-hackathon'
HOST = '8.141.114.201'
KNOWN_HOSTS = Path.home() / '.ssh' / 'known_hosts'
IDENTITY = Path.home() / '.ssh' / 'realtalk_ecs'


def public_files():
    # Import only the allowlist validator, never the remote install main().
    from install import FILES, allowed
    files = []
    for name in sorted(FILES):
        path = PROJECT / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f'Required release file is missing or a symlink: {name}')
        files.append(path)
    for folder in ['assets', 'downloads', 'server', 'scripts']:
        path = PROJECT / folder
        if path.exists():
            if path.is_symlink():
                raise RuntimeError(f'Release directory is a symlink: {folder}')
            for file in sorted(path.rglob('*')):
                relative = file.relative_to(PROJECT).as_posix()
                if file.is_symlink():
                    raise RuntimeError(f'Release entry is a symlink: {relative}')
                if file.is_file() and allowed(relative):
                    files.append(file)
    if not any(p.relative_to(PROJECT).as_posix() == 'server/app.py' for p in files):
        raise RuntimeError('server/app.py is missing')
    return files


def run_remote(client, command):
    _, stdout, stderr = client.exec_command(command, timeout=300)
    output, error = stdout.read().decode(), stderr.read().decode()
    status = stdout.channel.recv_exit_status()
    if status:
        # Installer source never reads access codes into stdout/stderr.
        raise RuntimeError(f'Remote deployment failed ({status}): {error[-5000:]}')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Perform the remote deployment (default only packages locally)')
    parser.add_argument('--source-sha', help='Git commit SHA; defaults to HEAD only if this project has its own .git')
    args = parser.parse_args()
    files = public_files()
    content = hashlib.sha256()
    blobs = []
    for path in files:
        name, data = path.relative_to(PROJECT).as_posix(), path.read_bytes()
        content.update(name.encode() + b'\0' + hashlib.sha256(data).digest())
        blobs.append((name, data))
    source_sha = args.source_sha
    if source_sha is None and (PROJECT / '.git').exists():
        source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT, text=True).strip()
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=PROJECT, text=True).strip():
            raise RuntimeError('Commit the project before deploying so the source SHA identifies this release')
    source_sha = source_sha or content.hexdigest()
    import re
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', source_sha):
        raise RuntimeError('source-sha must be a 40 or 64 character lowercase hexadecimal digest')
    release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + source_sha[:12] + '-' + uuid.uuid4().hex[:8]
    runtime = PROJECT / '.runtime'
    runtime.mkdir(exist_ok=True, mode=0o700)
    archive = runtime / ('release-' + release + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as package:
        for name, data in blobs:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            package.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {'release': release, 'sourceSha': source_sha, 'contentSha256': content.hexdigest(),
                'archiveSha256': digest, 'fileCount': len(blobs), 'files': [name for name, _ in blobs],
                'url': 'https://8.141.114.201/gotc/', 'executed': False}
    manifest_path = runtime / 'deployment.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if not args.execute:
        print(json.dumps({'packaged': str(archive), 'files': len(blobs), 'archiveSha256': digest,
                          'sourceSha': source_sha, 'remoteChanges': False}))
        return
    import paramiko
    client = paramiko.SSHClient()
    client.load_host_keys(str(KNOWN_HOSTS))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(HOST, username='root', key_filename=str(IDENTITY), look_for_keys=False, allow_agent=False, timeout=15)
    try:
        bootstrap = '''from pathlib import Path
import os
p=Path('/opt/gotc-hackathon')
if p.is_symlink() or (p.exists() and not (p/'.gotc-owned').is_file()):
    raise SystemExit('Unexpected GOTC directory; refusing deployment')
p.mkdir(exist_ok=True,mode=0o755)
m=p/'.gotc-owned'
if not m.exists():
    with m.open('x') as f: f.write('GOTC 2026 isolated deployment\\n')
q=p/'incoming'
if q.is_symlink(): raise SystemExit('Unexpected incoming symlink')
q.mkdir(exist_ok=True,mode=0o700)
os.chmod(q,0o700)
'''
        run_remote(client, 'python3 -c ' + shlex.quote(bootstrap))
        remote_archive = REMOTE_ROOT + '/incoming/' + archive.name
        remote_installer = REMOTE_ROOT + '/incoming/install-' + release + '.py'
        with client.open_sftp() as sftp:
            for local, remote in [(archive, remote_archive), (PROJECT / 'deploy' / 'install.py', remote_installer)]:
                # Exclusive create refuses symlinks and accidental reuse.
                with sftp.open(remote, 'wx') as output:
                    output.write(local.read_bytes())
                sftp.chmod(remote, 0o600)
        command = ['python3', remote_installer, '--archive', remote_archive, '--sha256', digest,
                   '--release', release, '--source-sha', source_sha]
        result = json.loads(run_remote(client, shlex.join(command)).strip())
        # This code is not an output artifact and must remain outside Git.
        private_file = runtime / 'admin-access.txt'
        temporary = runtime / 'admin-access.txt.pending'
        if temporary.exists() or temporary.is_symlink() or private_file.is_symlink():
            raise RuntimeError('Unexpected local admin-access path; deployment succeeded but private retrieval needs review')
        with client.open_sftp() as sftp:
            with sftp.open(REMOTE_ROOT + '/data/admin-access.txt', 'rb') as source:
                with temporary.open('xb') as output:
                    while True:
                        block = source.read(8192)
                        if not block:
                            break
                        output.write(block)
        os.chmod(temporary, 0o600)
        os.replace(temporary, private_file)
        manifest.update(result)
        manifest['executed'] = True
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'deployed': result['url'], 'release': release, 'sourceSha': source_sha,
                          'archiveSha256': digest, 'adminAccessSaved': True, 'oldServicesActive': True}))
    finally:
        client.close()


if __name__ == '__main__':
    main()
