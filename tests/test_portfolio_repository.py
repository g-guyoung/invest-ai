# -*- coding: utf-8 -*-
"""
src/portfolio/ 저장소 계층(Repository Pattern)에 대한 pytest 테스트.

실제 Supabase는 호출하지 않고 SupabaseClient를 mock으로 주입하여,
- SessionPortfolioRepository: 순수 세션(dict) 동작
- SupabasePortfolioRepository: Supabase 호출 위임이 올바른지
- repository_factory: 설정 상태에 따른 자동 선택/폴백
을 각각 검증한다.
"""

from __future__ import annotations

import pytest

from src.portfolio import repository_factory
from src.portfolio.constants import CATEGORIES, INITIAL_BALANCE
from src.portfolio.session_repository import SessionPortfolioRepository
from src.portfolio.supabase_repository import SupabasePortfolioRepository


# ============================================================================
# SessionPortfolioRepository
# ============================================================================

def test_session_repository_load_into_creates_all_categories():
    repo = SessionPortfolioRepository()
    state: dict = {}

    repo.load_into(state)

    assert set(state["portfolio"].keys()) == set(CATEGORIES)
    for category in CATEGORIES:
        book = state["portfolio"][category]
        assert book["cash"] == INITIAL_BALANCE
        assert book["holdings"] == {}
        assert book["history"] == []


def test_session_repository_load_into_does_not_overwrite_existing():
    repo = SessionPortfolioRepository()
    state = {"portfolio": {"기존": {"cash": 1, "holdings": {}, "history": []}}}

    repo.load_into(state)

    assert "기존" in state["portfolio"]
    assert "🇰🇷 한국 주식" not in state["portfolio"]


def test_session_repository_record_trade_is_noop():
    repo = SessionPortfolioRepository()
    # book에 변화가 없어야 하고, 예외도 없어야 한다.
    book = {"cash": 900_000, "holdings": {}, "history": []}
    result = repo.record_trade(
        "🇰🇷 한국 주식", "005930", "삼성전자", "BUY", 1.0, 70000.0, 70000.0, book,
    )
    assert result is None
    assert book == {"cash": 900_000, "holdings": {}, "history": []}


# ============================================================================
# SupabasePortfolioRepository (SupabaseClient mock 주입)
# ============================================================================

class _FakeSupabaseClient:
    """SupabaseClient의 최소 인터페이스를 흉내내는 스텁 (테스트용)."""

    def __init__(self, existing_wallets=None, existing_holdings=None, existing_trades=None):
        self.wallets = existing_wallets or {}
        self.holdings = existing_holdings or {}
        self.trades = existing_trades or {}
        self.calls: list[tuple] = []

    def health_check(self) -> bool:
        return True

    def get_wallet(self, user_id, category):
        self.calls.append(("get_wallet", category))
        return self.wallets.get(category)

    def init_wallet(self, user_id, category, initial_balance):
        self.calls.append(("init_wallet", category, initial_balance))
        self.wallets[category] = {"cash": initial_balance}
        return True

    def update_wallet_cash(self, user_id, category, cash):
        self.calls.append(("update_wallet_cash", category, cash))
        return True

    def get_holdings(self, user_id, category):
        return self.holdings.get(category, [])

    def upsert_holding(self, user_id, category, symbol, name, qty, avg_price):
        self.calls.append(("upsert_holding", category, symbol, qty, avg_price))
        return True

    def delete_holding(self, user_id, category, symbol):
        self.calls.append(("delete_holding", category, symbol))
        return True

    def add_wallet_trade(self, user_id, category, symbol, name, trade_type, qty, price,
                          amount, source="MANUAL", ai_signal=None, ai_confidence=None,
                          ai_reason=None):
        self.calls.append(("add_wallet_trade", category, symbol, trade_type, source))
        return True

    def get_wallet_trades(self, user_id, category, limit=20):
        return self.trades.get(category, [])


def test_supabase_repository_load_into_initializes_new_wallets():
    fake_client = _FakeSupabaseClient()
    repo = SupabasePortfolioRepository(client=fake_client)
    state: dict = {}

    repo.load_into(state)

    assert set(state["portfolio"].keys()) == set(CATEGORIES)
    for category in CATEGORIES:
        assert state["portfolio"][category]["cash"] == INITIAL_BALANCE
    # 지갑이 없었으므로 각 카테고리마다 init_wallet이 호출돼야 한다.
    assert len([c for c in fake_client.calls if c[0] == "init_wallet"]) == len(CATEGORIES)


def test_supabase_repository_load_into_restores_existing_state():
    fake_client = _FakeSupabaseClient(
        existing_wallets={"🇰🇷 한국 주식": {"cash": 850_000.0}},
        existing_holdings={
            "🇰🇷 한국 주식": [
                {"symbol": "005930", "name": "삼성전자", "qty": 2.0, "avg_price": 70000.0}
            ]
        },
    )
    repo = SupabasePortfolioRepository(client=fake_client)
    state: dict = {}

    repo.load_into(state)

    book = state["portfolio"]["🇰🇷 한국 주식"]
    assert book["cash"] == 850_000.0
    assert book["holdings"]["005930"]["qty"] == 2.0
    assert book["holdings"]["005930"]["avg_price"] == 70000.0


def test_supabase_repository_load_into_skips_if_already_loaded():
    fake_client = _FakeSupabaseClient()
    repo = SupabasePortfolioRepository(client=fake_client)
    state = {"portfolio": {"already": "loaded"}}

    repo.load_into(state)

    assert state["portfolio"] == {"already": "loaded"}
    assert fake_client.calls == []


def test_supabase_repository_record_trade_upserts_holding_when_present():
    fake_client = _FakeSupabaseClient()
    repo = SupabasePortfolioRepository(client=fake_client)
    book = {
        "cash": 930_000.0,
        "holdings": {"005930": {"name": "삼성전자", "qty": 1.0, "avg_price": 70000.0}},
        "history": [],
    }

    repo.record_trade(
        "🇰🇷 한국 주식", "005930", "삼성전자", "BUY", 1.0, 70000.0, 70000.0, book,
        source="AUTO_AI", ai_signal="BUY", ai_confidence=0.8, ai_reason="테스트",
    )

    assert ("update_wallet_cash", "🇰🇷 한국 주식", 930_000.0) in fake_client.calls
    assert ("upsert_holding", "🇰🇷 한국 주식", "005930", 1.0, 70000.0) in fake_client.calls
    assert ("add_wallet_trade", "🇰🇷 한국 주식", "005930", "BUY", "AUTO_AI") in fake_client.calls


def test_supabase_repository_record_trade_deletes_holding_when_absent():
    """전량 매도 후에는 holdings에서 symbol이 사라지므로 delete_holding이 호출돼야 한다."""
    fake_client = _FakeSupabaseClient()
    repo = SupabasePortfolioRepository(client=fake_client)
    book = {"cash": 1_070_000.0, "holdings": {}, "history": []}

    repo.record_trade(
        "🇰🇷 한국 주식", "005930", "삼성전자", "SELL", 1.0, 70000.0, 70000.0, book,
    )

    assert ("delete_holding", "🇰🇷 한국 주식", "005930") in fake_client.calls


def test_supabase_repository_record_trade_swallows_exceptions(monkeypatch):
    """저장 실패(네트워크 오류 등)가 매매 자체를 막으면 안 된다 — 예외를 올리지 않아야 한다."""

    class _BrokenClient(_FakeSupabaseClient):
        def update_wallet_cash(self, *args, **kwargs):
            raise ConnectionError("네트워크 오류")

    repo = SupabasePortfolioRepository(client=_BrokenClient())
    book = {"cash": 1.0, "holdings": {}, "history": []}

    # 예외가 전파되지 않아야 한다.
    repo.record_trade("🇰🇷 한국 주식", "005930", "삼성전자", "SELL", 1.0, 1.0, 1.0, book)


# ============================================================================
# repository_factory.get_repository()
# ============================================================================

@pytest.fixture(autouse=True)
def _reset_factory_cache():
    repository_factory.reset_cache()
    yield
    repository_factory.reset_cache()


def test_get_repository_falls_back_to_session_without_keys(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    repo = repository_factory.get_repository(force_refresh=True)

    assert isinstance(repo, SessionPortfolioRepository)


def test_get_repository_uses_supabase_when_configured_and_healthy(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")

    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(
        "src.portfolio.supabase_repository.SupabaseClient",
        lambda *a, **kw: fake_client,
    )

    repo = repository_factory.get_repository(force_refresh=True)

    assert isinstance(repo, SupabasePortfolioRepository)


def test_get_repository_falls_back_when_health_check_fails(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")

    class _UnhealthyClient(_FakeSupabaseClient):
        def health_check(self):
            return False

    monkeypatch.setattr(
        "src.portfolio.supabase_repository.SupabaseClient",
        lambda *a, **kw: _UnhealthyClient(),
    )

    repo = repository_factory.get_repository(force_refresh=True)

    assert isinstance(repo, SessionPortfolioRepository)


def test_get_repository_falls_back_when_init_raises(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")

    def _boom(*a, **kw):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr("src.portfolio.supabase_repository.SupabaseClient", _boom)

    repo = repository_factory.get_repository(force_refresh=True)

    assert isinstance(repo, SessionPortfolioRepository)


def test_get_repository_caches_result(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    repo1 = repository_factory.get_repository()
    repo2 = repository_factory.get_repository()

    assert repo1 is repo2
