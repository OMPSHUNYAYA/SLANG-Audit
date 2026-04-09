rules = [
    ("revenue_valid", "true", lambda s: s.get("contracts_supported") == "true"),
    ("expense_valid", "true", lambda s: s.get("costs_supported") == "true"),
    ("structural_profit", "300", lambda s: s.get("revenue_valid") == "true" and s.get("expense_valid") == "true"),
    ("audit", "pass", lambda s: s.get("structural_profit") == "300"),
]

state = {
    "contracts_supported": "partial",
    "costs_supported": "true",
    "reported_profit": "300"
}

changed = True

while changed:
    changed = False
    for key, value, cond in rules:
        if cond(state) and state.get(key) != value:
            state[key] = value
            changed = True

ordered = {
    k: state[k]
    for k in [
        "contracts_supported",
        "costs_supported",
        "reported_profit",
        "revenue_valid",
        "expense_valid",
        "structural_profit",
        "audit",
    ]
    if k in state
}

print(ordered)