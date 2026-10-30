"""Copy an event database with SQLite's backup API, without overwriting a destination."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3


def copy_database(source, destination):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if not source.is_file():raise ValueError('Source database does not exist')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    reader=None;writer=None
    try:
        reader=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        if reader.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Source integrity check failed')
        writer=sqlite3.connect(destination)
        reader.backup(writer)
        if writer.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or writer.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Copied database validation failed')
        tables=[row[0] for row in writer.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        rows={table:writer.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0] for table in tables}
        return {'source':str(source),'destination':str(destination),'integrity':'ok','tables':len(tables),'rows':rows}
    except Exception:
        if writer:writer.close();writer=None
        destination.unlink(missing_ok=True)
        raise
    finally:
        if writer:writer.close()
        if reader:reader.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('backup','restore'))
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path,help='New file only; restore never replaces an active database')
    args=parser.parse_args()
    try:result=copy_database(args.source,args.destination)
    except (OSError,ValueError,sqlite3.Error) as error:parser.exit(1,str(error)+'\n')
    print(json.dumps({'operation':args.operation,**result},ensure_ascii=False))


if __name__=='__main__':main()
