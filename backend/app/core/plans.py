"""Configuración de planes (sección 6 del documento). None = ilimitado."""

PLANS: dict[str, dict] = {
    "free": {
        "label": "Gratuito",
        "price_bs": 0,
        "max_packages": 30,
        "max_notifications": 30,
        "max_ai": 10,
        "max_operators": 1,
        "granularities": [],
        "export": False,
        "ai_advanced": False,
    },
    "basic": {
        "label": "Básico",
        "price_bs": 99,
        "max_packages": 250,
        "max_notifications": 700,
        "max_ai": 50,
        "max_operators": 2,
        "granularities": ["day"],
        "export": False,
        "ai_advanced": False,
    },
    "premium": {
        "label": "Premium",
        "price_bs": 199,
        "max_packages": None,
        "max_notifications": 2000,
        "max_ai": 200,
        "max_operators": None,
        "granularities": ["day", "week", "month", "year"],
        "export": True,
        "ai_advanced": True,
    },
}

METRIC_LIMIT_KEY = {
    "packages": "max_packages",
    "notifications": "max_notifications",
    "ai_queries": "max_ai",
}


def plan_of(name: str) -> dict:
    return PLANS.get(name, PLANS["free"])
