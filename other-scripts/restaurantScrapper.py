import requests
import json
from datetime import datetime

# Yelp API Key (Replace with your actual key)
API_KEY = "7OrE2CQbOijnDqXbGJPrliAeWzJPG63O6idIV_6i4DiZ0C6vLY_GEs3BNS44XPXzN76OtnuLPB60dVno7U1BZQ4EgR1Ec0zbmd60pfp20Ser877J-3vn-jMHBjDkaHYx"

# Yelp API Headers
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Cuisines & More Manhattan Neighborhoods
cuisines = ["Thai", "Mexican", "Chinese", "Italian", "Indian"]
neighborhoods = [
    "Financial District, Manhattan, NY",
    "East Village, Manhattan, NY",
    "SoHo, Manhattan, NY",
    "Tribeca, Manhattan, NY",
    "Upper West Side, Manhattan, NY",
    "Harlem, Manhattan, NY",
    "Chelsea, Manhattan, NY",
    "Upper East Side, Manhattan, NY",
    "Midtown, Manhattan, NY",
    "Lower Manhattan, Manhattan, NY"
]

def fetch_restaurants(cuisine, total=250):
    """Fetch 1000+ unique restaurants per cuisine from multiple Manhattan neighborhoods."""
    url = "https://api.yelp.com/v3/businesses/search"
    unique_restaurants = {}

    for neighborhood in neighborhoods:
        offset = 0
        while len(unique_restaurants) < total and offset < 100:  # Stay within Yelp's 240 limit
            params = {
                "term": f"{cuisine} food",
                "location": neighborhood,
                "categories": "restaurants",
                "limit": min(30, total - len(unique_restaurants)),  
                "offset": offset
            }

            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code != 200:
                print(f"Error fetching {cuisine} in {neighborhood}: {response.json()}")
                break

            data = response.json().get("businesses", [])
            if not data:
                break  # Stop if no results

            for r in data:
                unique_restaurants[r["id"]] = {
                    "BusinessID": r["id"],
                    "Name": r["name"],
                    "Address": r["location"].get("address1", ""),
                    "Coordinates": {
                        "lat": r["coordinates"]["latitude"],
                        "lon": r["coordinates"]["longitude"]
                    },
                    "NumReviews": r["review_count"],
                    "Rating": r["rating"],
                    "ZipCode": r["location"].get("zip_code", ""),
                    "Cuisine": cuisine,
                    "InsertedAtTimestamp": str(datetime.utcnow())
                }

            offset += 30  # Move to the next batch

        print(f"{cuisine} ({neighborhood}): {len(unique_restaurants)} collected so far...")

        if len(unique_restaurants) >= total:
            break  # Stop once we have enough unique restaurants

    print(f"Final {cuisine} count: {len(unique_restaurants)}")
    return list(unique_restaurants.values())[:total]

# Fetch & Save Restaurants Locally
all_restaurants = []
for cuisine in cuisines:
    print(f"Fetching {cuisine} restaurants from Manhattan...")
    restaurants = fetch_restaurants(cuisine, 250)
    all_restaurants.extend(restaurants)

# Save to JSON File
with open("other-scripts/restaurants.json", "w") as f:
    json.dump(all_restaurants, f, indent=4)

print(f"Total {len(all_restaurants)} restaurants saved to 'restaurants.json'!")