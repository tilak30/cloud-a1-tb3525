import json
import boto3
from pathlib import Path
from datetime import datetime

# Initialize DynamoDB
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
TABLE_NAME = "yelp-restaurants"

# Local JSON file
LOCAL_FILE = Path("/Users/tilakbhansali/Documents/NYU/Fall2025/cloud computing/cloud-a1-tb3525/other-scripts/restaurants.json")


def load_restaurants_from_local(file_path: Path):
    """Read and parse restaurant data from a local JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} restaurants from {file_path}")
    return data


def insert_to_dynamodb(restaurants, table_name: str):
    """Insert restaurant entries into DynamoDB."""
    table = dynamodb.Table(table_name)

    for entry in restaurants:
        try:
            item = {
                # changed key to match DynamoDB partition key
                "business_id": entry.get("business_id") or entry.get("BusinessID"),

                "Name": entry.get("Name"),
                "Address": entry.get("Address"),
                "Coordinates": {
                    "lat": str(entry["Coordinates"].get("lat") or entry["Coordinates"].get("latitude")),
                    "lon": str(entry["Coordinates"].get("lon") or entry["Coordinates"].get("longitude")),
                },
                "NumReviews": entry.get("NumReviews"),
                "Rating": str(entry.get("Rating")),
                "ZipCode": entry.get("ZipCode"),
                "Cuisine": entry.get("Cuisine"),
                # add timestamp if missing
                "InsertedAtTimestamp": entry.get("InsertedAtTimestamp") or datetime.utcnow().isoformat()
            }

            if not item["business_id"]:
                print("Skipping record with missing business_id")
                continue

            table.put_item(Item=item)

        except Exception as e:
            print(f"Error inserting record: {e}")

    print(f"Inserted {len(restaurants)} records into DynamoDB.")


def main():
    """Main function for local execution."""
    try:
        restaurants = load_restaurants_from_local(LOCAL_FILE)
        insert_to_dynamodb(restaurants, TABLE_NAME)
        print("All records successfully uploaded to DynamoDB.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
