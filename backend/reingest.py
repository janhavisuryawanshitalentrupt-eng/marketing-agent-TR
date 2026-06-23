"""One-off: clear the brand library and re-ingest with the new topical captions + PDF de-spacing."""
import asyncio

from app.db import SessionLocal, init_db
from app.knowledge.ingest import run_ingest
from app.models import BrandChunk, SourceFile

init_db()
db = SessionLocal()
nc = db.query(BrandChunk).delete()
nf = db.query(SourceFile).delete()
db.commit()
db.close()
print(f"[reset] cleared {nf} source_files, {nc} brand_chunks. Re-ingesting…", flush=True)
print(asyncio.run(run_ingest()), flush=True)
