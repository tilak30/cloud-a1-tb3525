import os
import urllib3
import base64
import json

OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT")
OS_USERNAME = os.getenv("OS_USERNAME")
OS_PASSWORD = os.getenv("OS_PASSWORD")
INDEX_NAME = "restaurants"

http = urllib3.PoolManager()
auth_header = base64.b64encode(f"{OS_USERNAME}:{OS_PASSWORD}".encode()).decode()
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Basic {auth_header}"
}

# Get document count
count_url = f"{OPENSEARCH_ENDPOINT}/{INDEX_NAME}/_count"
response = http.request("GET", count_url, headers=headers)
data = json.loads(response.data.decode("utf-8"))
print(f"Documents in '{INDEX_NAME}' index:", data.get("count", 0))
