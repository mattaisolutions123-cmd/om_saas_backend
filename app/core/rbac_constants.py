from typing import Dict, Any, List

ALL_MODULES = [
    "trends",
    "tasks",
    "tickets",
    "payments",
    "clients",
    "services",
    "inventory",
    "shop",
    "reports",
    "ads",
    "settings",
]

ROLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "super_admin": {
        "id": "role_super_admin",
        "slug": "super_admin",
        "name": "Super Admin (Owner)",
        "description": "Enterprise administrator with unrestricted access across all branches and modules",
        "is_system": True,
        "permissions": [{"module": m, "access_level": "FULL"} for m in ALL_MODULES],
    },
    "owner": {
        "id": "role_super_admin",
        "slug": "super_admin",
        "name": "Super Admin (Owner)",
        "description": "Enterprise administrator with unrestricted access across all branches and modules",
        "is_system": True,
        "permissions": [{"module": m, "access_level": "FULL"} for m in ALL_MODULES],
    },
    "branch_manager": {
        "id": "role_branch_manager",
        "slug": "branch_manager",
        "name": "Branch Manager",
        "description": "Manages local branch operations, staff, local inventory, tickets and finances",
        "is_system": True,
        "permissions": [
            {"module": "trends", "access_level": "BRANCH"},
            {"module": "tasks", "access_level": "FULL"},
            {"module": "tickets", "access_level": "FULL"},
            {"module": "payments", "access_level": "BRANCH"},
            {"module": "clients", "access_level": "FULL"},
            {"module": "services", "access_level": "FULL"},
            {"module": "inventory", "access_level": "BRANCH"},
            {"module": "shop", "access_level": "FULL"},
            {"module": "reports", "access_level": "BRANCH"},
            {"module": "ads", "access_level": "FULL"},
            {"module": "settings", "access_level": "RESTRICTED"},
        ],
    },
    "cashier": {
        "id": "role_cashier",
        "slug": "cashier",
        "name": "Desk Receptionist / POS Cashier",
        "description": "Front-counter reception, client intake, POS billing, ticket creation, cash register",
        "is_system": True,
        "permissions": [
            {"module": "trends", "access_level": "VIEW_ONLY"},
            {"module": "tasks", "access_level": "ASSIGNED_ONLY"},
            {"module": "tickets", "access_level": "COUNTER"},
            {"module": "payments", "access_level": "REGISTER_ONLY"},
            {"module": "clients", "access_level": "FULL"},
            {"module": "services", "access_level": "VIEW_ONLY"},
            {"module": "inventory", "access_level": "VIEW_ONLY"},
            {"module": "shop", "access_level": "POS_FULL"},
            {"module": "reports", "access_level": "DAILY_REGISTER"},
            {"module": "ads", "access_level": "VIEW_ONLY"},
            {"module": "settings", "access_level": "NONE"},
        ],
    },
    "technician": {
        "id": "role_technician",
        "slug": "technician",
        "name": "Field / Lab Technician",
        "description": "Performs diagnostics, repairs, part requests, onsite jobs, and updates work order stages",
        "is_system": True,
        "permissions": [
            {"module": "trends", "access_level": "NONE"},
            {"module": "tasks", "access_level": "ASSIGNED_ONLY"},
            {"module": "tickets", "access_level": "ASSIGNED_TECH"},
            {"module": "payments", "access_level": "NONE"},
            {"module": "clients", "access_level": "VIEW_ONLY"},
            {"module": "services", "access_level": "VIEW_ONLY"},
            {"module": "inventory", "access_level": "REQUEST_ONLY"},
            {"module": "shop", "access_level": "NONE"},
            {"module": "reports", "access_level": "MY_PERFORMANCE"},
            {"module": "ads", "access_level": "VIEW_ONLY"},
            {"module": "settings", "access_level": "NONE"},
        ],
    },
}


def get_role_definition(slug: str) -> Dict[str, Any]:
    norm_slug = (slug or "super_admin").lower().strip()
    return ROLE_DEFINITIONS.get(norm_slug, ROLE_DEFINITIONS["super_admin"])
