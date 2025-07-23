from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DocumentUploadResponse(BaseModel):
    id: str
    file_name: str
    file_type: str
    file_url: str
    uploaded_at: datetime 