import logging
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.models.pricing import PricingQuote
from app.schemas.pricing import PricingQuoteCreate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

class PricingService:
    @staticmethod
    async def create_quote(db: AsyncSession, quote_in: PricingQuoteCreate):
        # Input validation
        if not quote_in.item_name or not quote_in.item_name.strip():
            raise HTTPException(status_code=422, detail="Item name must not be empty.")
        if not quote_in.supplier_id or not quote_in.supplier_id.strip():
            raise HTTPException(status_code=422, detail="Supplier ID must not be empty.")
        if quote_in.price is None or quote_in.price <= 0:
            raise HTTPException(status_code=422, detail="Price must be a positive number.")
        try:
            quote = PricingQuote(**quote_in.dict())
            db.add(quote)
            await db.commit()
            await db.refresh(quote)
            return quote
        except SQLAlchemyError as e:
            logging.error(f"Database error while creating quote: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create quote due to a database error.")
        except Exception as e:
            logging.error(f"Unexpected error while creating quote: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="An unexpected error occurred while creating quote.")

    @staticmethod
    async def get_quote(db: AsyncSession, quote_id: int) -> Optional[PricingQuote]:
        try:
            result = await db.execute(select(PricingQuote).where(PricingQuote.id == quote_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logging.error(f"Database error while fetching quote: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error while fetching quote: {e}")
            return None 