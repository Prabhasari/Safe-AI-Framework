import requests

CA_URL = "http://127.0.0.1:8011"
GATEWAY_URL = "http://127.0.0.1:8012"

def main():
    plugin_id = "plugin_good_1"

    r = requests.post(f"{CA_URL}/issue-cert", json={"plugin_id": plugin_id, "ttl_hours": 3})
    r.raise_for_status()
    cert = r.json()["certificate_pem"]

    onboard = requests.post(
        f"{GATEWAY_URL}/onboard",
        json={
            "plugin_id": plugin_id,
            "plugin_name": "Good Plugin",
            "role": "code_generator",
            "declared_intent": "generate_code",
            "certificate_pem": cert,
        },
    )
    onboard.raise_for_status()
    data = onboard.json()
    token = data["access_token"]

    print("Onboard response:", data)

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{GATEWAY_URL}/core/plugins", headers=headers)
    print("Core /core/plugins status:", resp.status_code)
    print(resp.text)

if __name__ == "__main__":
    main()