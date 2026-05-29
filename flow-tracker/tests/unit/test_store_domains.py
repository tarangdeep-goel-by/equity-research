"""Tests for the FlowStore domain-mixin split (refactor P1.4).

Verifies the facade contract: every domain method is reachable both flat
(store.method) and namespaced (store.domain.method), pointing at the same
instance/connection.
"""

from __future__ import annotations

import pytest

from flowtracker.alert_models import Alert
from flowtracker.store import FlowStore
from flowtracker.store_domains import Namespace
from flowtracker.store_domains.portfolio import PortfolioMixin


class TestPortfolioNamespace:
    def test_flat_and_namespace_are_same_instance(self, store: FlowStore):
        assert isinstance(store.portfolio, Namespace)
        # Both styles hit the same connection → a flat write is visible via ns.
        store.upsert_alert(Alert(symbol="SBIN", condition_type="price_below", threshold=750.0))
        assert len(store.get_active_alerts()) == 1
        assert len(store.portfolio.get_active_alerts()) == 1

    def test_namespace_write_visible_flat(self, store: FlowStore):
        store.portfolio.upsert_alert(
            Alert(symbol="INFY", condition_type="pe_above", threshold=30.0)
        )
        assert store.get_active_alerts()[0].symbol == "INFY"

    def test_namespace_exposes_only_its_methods(self, store: FlowStore):
        assert "get_active_alerts" in dir(store.portfolio)
        assert "upsert_portfolio_holding" in dir(store.portfolio)
        # A method from another domain is NOT on this namespace.
        with pytest.raises(AttributeError):
            _ = store.portfolio.get_flows

    def test_mixin_public_methods_are_namespaced(self, store: FlowStore):
        public = {
            n for n, v in vars(PortfolioMixin).items()
            if callable(v) and not n.startswith("_")
        }
        for name in public:
            assert hasattr(store.portfolio, name)
            assert hasattr(store, name)  # flat access preserved
