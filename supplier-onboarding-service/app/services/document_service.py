from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
from typing import List
from app.models.document import Document
import os
import uuid

UPLOAD_DIR = "uploads/"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class DocumentService:
    async def upload_documents(self, db: AsyncSession, supplier_id: str, files: List[UploadFile]):
        responses = []
        for file in files:
            file_id = str(uuid.uuid4())
            file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
            with open(file_path, "wb") as f:
                f.write(await file.read())
            doc = Document(
                id=file_id,
                supplier_id=supplier_id,
                file_name=file.filename,
                file_type=file.content_type,
                file_url=file_path
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            responses.append(doc)
        return responses 