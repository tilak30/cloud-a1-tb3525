import os
import json
import random
import base64
import boto3
import urllib3

# ================== Configuration ==================
REGION = "us-east-1"

# DynamoDB table
DDB_RESTAURANTS_TABLE = "yelp-restaurants"

# SQS
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")  # DiningRequests queue

# OpenSearch
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT")
OS_USERNAME = os.getenv("OS_USERNAME")
OS_PASSWORD = os.getenv("OS_PASSWORD")
INDEX_NAME = "restaurants"

# SES
SENDER_EMAIL = os.getenv("SENDER_EMAIL")  # Must be verified in SES sandbox

# ================== AWS Clients ==================
dynamodb = boto3.resource("dynamodb", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
ses = boto3.client("ses", region_name=REGION)
http = urllib3.PoolManager()

# Base64 encoded credentials for OpenSearch
AUTH_HEADER = base64.b64encode(f"{OS_USERNAME}:{OS_PASSWORD}".encode()).decode()


# ================== Helper Functions ==================

def query_restaurants_from_opensearch(cuisine, count=3):
    """Query OpenSearch for random restaurant IDs matching a cuisine"""
    search_url = f"{OPENSEARCH_ENDPOINT}/{INDEX_NAME}/_search"
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {AUTH_HEADER}"}

    query = {
        "size": 50,  # Fetch more to randomize locally
        "query": {
            "function_score": {
                "query": {"match": {"Cuisine": cuisine}},
                "random_score": {}
            }
        }
    }

    response = http.request("GET", search_url, body=json.dumps(query).encode("utf-8"), headers=headers)
    try:
        hits = json.loads(response.data.decode("utf-8"))["hits"]["hits"]
    except Exception as e:
        print("Error parsing OpenSearch response:", e)
        return []

    restaurant_ids = [h["_source"]["RestaurantID"] for h in hits]
    return random.sample(restaurant_ids, min(count, len(restaurant_ids)))


def fetch_restaurant_details(business_id):
    """Retrieve restaurant info from DynamoDB using business_id"""
    table = dynamodb.Table(DDB_RESTAURANTS_TABLE)
    response = table.get_item(Key={"business_id": business_id})
    return response.get("Item")


def format_email_body(restaurants, cuisine):
    """Build the text body for SES email"""
    body = f"Hello!\n\nHere are some recommended {cuisine} restaurants for you:\n\n"
    for i, r in enumerate(restaurants, start=1):
        body += (
            f"{i}. {r.get('Name', 'Unknown')}\n"
            f"  📍 Address: {r.get('Address', 'N/A')}\n"
            f"  ⭐ Rating: {r.get('Rating', 'N/A')} ({r.get('NumReviews', '0')} reviews)\n"
            f"  🏙️ Zip Code: {r.get('ZipCode', 'N/A')}\n\n"
        )
    body += "Enjoy your meal!\n\n- Your Dining Bot"
    return body


def send_email(to_email, restaurants, cuisine):
    """Send restaurant recommendations via SES"""
    try:
        response = ses.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": f"Your {cuisine} Restaurant Recommendations"},
                "Body": {"Text": {"Data": format_email_body(restaurants, cuisine)}}
            }
        )
        return response
    except Exception as e:
        print("Error sending email:", e)
        return None


# ================== Lambda Handler ==================
def lambda_handler(event, context):
    """Main Lambda to process dining suggestions"""
    try:
        #Step 1: Pull SQS message
        # sqs_message, receipt_handle = receive_sqs_message(event[])
        message = event["Records"][0]
        print(f"{message}")
        receipt_handle = message["receiptHandle"]
        sqs_message = json.loads(message["body"])
        if not sqs_message:
            print("No messages in the SQS queue.")
            return {"status": "No messages"}

        # sqs_message = {"Cuisine": "Italian", "Email": "bhansalitilak3009@gmail.com"}
        # receipt_handle = None

        cuisine = sqs_message["Cuisine"]
        email = sqs_message["Email"]

        print(f"Processing request for cuisine: {cuisine} and email: {email}")
        # Step 2: Query restaurant IDs from OpenSearch
        restaurant_ids = query_restaurants_from_opensearch(cuisine)

        if not restaurant_ids:
            print(f"No restaurants found for cuisine: {cuisine}")
            return {"status": "No restaurants found"}

        # Step 3: Fetch full restaurant details from DynamoDB
        restaurants = []
        for rid in restaurant_ids:
            item = fetch_restaurant_details(rid)
            if item:
                restaurants.append(item)
    
        if not restaurants:
            print("No restaurant details found in DynamoDB")
            return {"status": "No details found"}

        # # Step 4: Send email
        # email_res = send_email(email, restaurants, cuisine)
        # if email_res:
        # # Only delete the message if email was sent successfully
        #     sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
        #     print(f"Email sent successfully to {email} and SQS message deleted.")
        # else:
        #     # Don't delete message; SQS will retry until maxReceiveCount
        #     print(f"Failed to send email to {email}. Message will remain in queue for retry.")
        # Step 4: Send email
        email_response = send_email(email, restaurants, cuisine)

        if not email_response:
            # Raise an exception to prevent Lambda from deleting the message
            raise Exception(f"Failed to send email to {email}")
        else:
            print(f"Email sent successfully to {email}.")

        # send_email(email, restaurants, cuisine)

        # # Step 5: Delete processed message from SQS
        # sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
        # print(f"Email sent successfully to {email} and SQS message deleted.")

        return {"status": "Success"}

    except Exception as e:
        print("Error in Lambda function:", e)
        raise
