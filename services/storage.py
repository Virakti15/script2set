"""Single private workspace storage. SQLite contains both projects and image bytes.

DATA_DIR must be on a persistent disk in production. No temporary export files.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from .schema import UserError


class Store:
    def __init__(self, directory):
        self.directory=Path(directory)

    @contextmanager
    def connect(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(self.directory/'script2set.sqlite3',timeout=20)
        conn.row_factory=sqlite3.Row
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, info TEXT NOT NULL, data BLOB NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated TEXT NOT NULL, data TEXT NOT NULL)')
            yield conn
            conn.commit()
        finally:
            conn.close()

    def put_image(self, data, info):
        asset_id=str(uuid.uuid4())
        info={**info,'asset_id':asset_id,'approved':False,'status':'review','stale':False}
        with self.connect() as db:
            db.execute('INSERT INTO assets VALUES (?,?,?)',(asset_id,json.dumps(info),data))
        return info

    def image(self, asset_id):
        if not isinstance(asset_id,str): raise UserError('Choose a saved storyboard image.',400)
        with self.connect() as db: row=db.execute('SELECT * FROM assets WHERE id=?',(asset_id,)).fetchone()
        if not row: raise UserError('Storyboard image is unavailable on this server. Upload or generate it again.',404)
        return json.loads(row['info']),bytes(row['data'])

    def approve(self, asset_id, approved):
        info,data=self.image(asset_id)
        info.update(approved=approved,status='approved' if approved else 'review')
        with self.connect() as db: db.execute('UPDATE assets SET info=? WHERE id=?',(json.dumps(info),asset_id))
        return info,data

    def save_project(self, project):
        project_id=project.get('serverId') or str(uuid.uuid4())
        try: uuid.UUID(project_id)
        except (ValueError,TypeError,AttributeError): raise UserError('Invalid saved project identifier.') from None
        project={**project,'serverId':project_id}
        encoded=json.dumps(project,ensure_ascii=False)
        if len(encoded.encode())>30_000_000: raise UserError('Project exceeds the 30 MB storage limit.',413)
        now=datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, updated=excluded.updated, data=excluded.data',
                       (project_id,str(project.get('title','Untitled production'))[:200],now,encoded))
        return project_id

    def projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,title,updated FROM projects ORDER BY updated DESC LIMIT 100')]

    def project(self, project_id):
        with self.connect() as db: row=db.execute('SELECT data FROM projects WHERE id=?',(project_id,)).fetchone()
        if not row: raise UserError('Saved project not found.',404)
        return json.loads(row['data'])
