"""Domain stores — FlowStore split into per-domain mixins (refactor P1.4).

FlowStore was a single ~7k-line class. We split it into domain mixin classes
(one per file here) that FlowStore inherits. Mixins hold only methods; the
shared infrastructure (sqlite connection ``self._conn``, schema init,
``_validate_row``, transaction/commit, context manager) stays in ``store.py``.

Because mixins compose into the *same* FlowStore instance via MRO, every method
keeps working exactly as before — ``self._conn`` and any cross-method
``self.other_method()`` call resolve unchanged. This makes the split a pure,
behavior-preserving cut-paste.

Two access styles are supported (both point at the same instance):
- **flat** (unchanged): ``store.get_portfolio_holdings()``
- **namespaced** (new, additive): ``store.portfolio.get_portfolio_holdings()``
  via the :class:`Namespace` accessors wired up in ``FlowStore.__init__``.
"""

from __future__ import annotations

from typing import Any


class Namespace:
    """Exposes one domain mixin's public methods on the facade instance, so
    ``store.<domain>.<method>()`` delegates to the same FlowStore object that
    backs the flat API. Purely additive — the flat methods keep working."""

    def __init__(self, store: Any, mixin_cls: type) -> None:
        self._store = store
        self._names = frozenset(
            name
            for name, val in vars(mixin_cls).items()
            if callable(val) and not name.startswith("_")
        )

    def __getattr__(self, name: str) -> Any:
        # _store / _names are real instance attrs, so they never reach here;
        # only domain method lookups do.
        if name in self._names:
            return getattr(self._store, name)
        raise AttributeError(
            f"{name!r} is not a method of this domain namespace"
        )

    def __dir__(self) -> list[str]:
        return sorted(self._names)


__all__ = ["Namespace"]
