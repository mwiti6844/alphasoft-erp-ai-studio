"""Module-scope → router resolution. Unknown scopes fail loudly."""

from __future__ import annotations

from app.agents.modules.base import ModuleRouter
from app.agents.modules.catalog import CATALOG_ROUTER
from app.agents.modules.inventory import INVENTORY_ROUTER
from app.agents.modules.pos import POS_ROUTER


class UnknownModuleScopeError(ValueError):
    pass


ROUTERS: dict[str, ModuleRouter] = {
    router.scope: router
    for router in (CATALOG_ROUTER, INVENTORY_ROUTER, POS_ROUTER)
}


def router_for_scope(scope: str) -> ModuleRouter:
    router = ROUTERS.get(scope)
    if router is None:
        supported = ", ".join(sorted(ROUTERS))
        raise UnknownModuleScopeError(
            f"Unknown module scope '{scope}'. Supported: {supported}"
        )
    return router
