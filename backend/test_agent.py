import requests

payload = {
    "name": "AuditBot 9000",
    "declared_task": "Audit the main ledger for discrepancies in external transactions.",
    "base_spend_cap": 500.0,
    "merchant_category_scope": ["CLOUD_HOSTING", "SOFTWARE_SERVICES"]
}

response = requests.post("http://127.0.0.1:8000/agents", json=payload)
print(response.status_code)
print(response.json())
