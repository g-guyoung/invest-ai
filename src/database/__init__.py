# -*- coding: utf-8 -*-
"""Database module for Invest AI."""

from .supabase_client import SupabaseClient, SupabaseError

__all__ = ["SupabaseClient", "SupabaseError"]
