import time
import requests

CA_URL = "http://127.0.0.1:8011"
GATEWAY_URL = "http://127.0.0.1:8012"

def main():
    plugin_id = "plugin_evil_1"

    r = requests.post(f"{CA_URL}/issue-cert", json={"plugin_id": plugin_id, "ttl_hours": 3})
    r.raise_for_status()
    cert = r.json()["certificate_pem"]

    onboard = requests.post(
        f"{GATEWAY_URL}/onboard",
        json={
            "plugin_id": plugin_id,
            "plugin_name": "Evil Plugin",
            "role": "unknown",
            "declared_intent": "probe",
            "certificate_pem": cert,
        },
    )
    onboard.raise_for_status()
    token = onboard.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("Onboard response (evil):", onboard.json())

    for i in range(0, 120):
        resp = requests.get(f"{GATEWAY_URL}/core/does-not-exist", headers=headers)
        print(f"[{i}] status={resp.status_code}")
        time.sleep(0.05)

if __name__ == "__main__":
    main()