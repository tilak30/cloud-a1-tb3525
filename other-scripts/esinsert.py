import json
import boto3
import urllib3
import random
import base64
import os
from pathlib import Path

# ===== Configuration =====
REGION = "us-east-1"
DDB_TABLE = "yelp-restaurants"
INDEX_NAME = "restaurants"
CUISINES = ["Indian", "Chinese", "Mexican", "Italian", "Thai"]

# OpenSearch credentials via environment variables
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT")
OS_USERNAME = os.getenv("OS_USERNAME")
OS_PASSWORD = os.getenv("OS_PASSWORD")

if not OPENSEARCH_ENDPOINT or not OS_USERNAME or not OS_PASSWORD:
    raise ValueError("Please set OPENSEARCH_ENDPOINT, OS_USERNAME, and OS_PASSWORD environment variables")

# Initialize AWS resources
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(DDB_TABLE)
http = urllib3.PoolManager()


# ===== Helper Functions =====
def get_restaurants_by_cuisine(cuisine_name):
    """
    Pull all restaurants of a given cuisine from DynamoDB.
    """
    response = table.scan(
        FilterExpression="Cuisine = :cuisine",
        ExpressionAttributeValues={":cuisine": cuisine_name}
    )
    records = response.get("Items", [])
    random.shuffle(records)
    return records


def index_to_opensearch(records):
    """
    Index restaurant data into OpenSearch.
    """
    credentials = f"{OS_USERNAME}:{OS_PASSWORD}"
    encoded_auth = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    for item in records:
        document = {
            "RestaurantID": item["business_id"],
            "Cuisine": item["Cuisine"]
        }

        url = f"{OPENSEARCH_ENDPOINT}/{INDEX_NAME}/_doc/{item['business_id']}"
        response = http.request("PUT", url, headers=headers, body=json.dumps(document).encode("utf-8"))

        if response.status not in (200, 201):
            print(f"[!] Failed to insert {item['business_id']} — HTTP {response.status}")


# ===== Main Local Execution =====
def main():
    all_records = []

    for cuisine in CUISINES:
        entries = get_restaurants_by_cuisine(cuisine)
        print(f"Fetched {len(entries)} records for cuisine: {cuisine}")
        all_records.extend(entries)

    print(f"Total records to push to OpenSearch: {len(all_records)}")
    index_to_opensearch(all_records)
    print("All records successfully pushed to OpenSearch!")


if __name__ == "__main__":
    main()
