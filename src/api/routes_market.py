"""
Market Intelligence Lab — Market & Stocks API Router (Milestone B6.4).
Exposes routes for individual stock tearsheets, dynamic status polling, and historical bars.
"""

from fastapi import APIRouter
from src.api.main import app

# Provide router interface for modular API mounting
market_router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])

# Re-export key handlers from main application
__all__ = ["market_router"]
