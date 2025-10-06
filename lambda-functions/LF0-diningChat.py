import json
import os
import boto3
from datetime import datetime

# --- Configuration (Best Practice: Use Environment Variables) ---
# Initialize Lex client. Region is fetched from Lambda environment automatically.
REGION = os.environ.get('AWS_REGION', 'us-east-1')
lex_client = boto3.client('lexv2-runtime', region_name=REGION)

# Bot details retrieved from environment variables for easy updates
BOT_ID = os.environ.get('BOT_ID')
BOT_ALIAS_ID = os.environ.get('BOT_ALIAS_ID')
LOCALE_ID = os.environ.get('LOCALE_ID', 'en_US')

# Standard headers for API Gateway response (especially for CORS)
HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*"
}

def lambda_handler(event, context):
    """
    Handles API Gateway requests, sends text to Lex V2, and returns a structured chat response.
    """
    try:
        # 1. Input Parsing and Validation
        
        # Ensure the body exists and parse it
        if "body" not in event or not event["body"]:
            raise ValueError("Missing request body.")
            
        body = json.loads(event["body"])

        # Validate the specific chat message format (e.g., from a web chat client)
        messages = body.get("messages", [])
        if not (messages and 
                "unstructured" in messages[0] and 
                "text" in messages[0]["unstructured"]):
            raise ValueError("Missing or invalid message format in request body.")

        # Extract message details
        user_message = messages[0]["unstructured"]["text"].strip()
        # Use a user-specific ID for session continuity (Best Practice)
        user_id = messages[0]["unstructured"].get("id", "default-user")
        
        print(f"User ID: {user_id}, Text: {user_message}")

        # 2. Call Lex Bot
        
        lex_response = lex_client.recognize_text(
            botId=BOT_ID,
            botAliasId=BOT_ALIAS_ID,
            localeId=LOCALE_ID,
            sessionId=user_id, # Key for maintaining conversation history
            text=user_message
        )

        # 3. Process Lex Response
        
        # Extract the main response message content
        lex_response_message = (
            lex_response.get("messages", [{}])[0].get("content", "Sorry, I didn't understand that.")
        )
        
        # 4. Construct Structured API Response
        
        formatted_response = {
            "messages": [
                {
                    "type": "unstructured",
                    "unstructured": {
                        "id": "bot-response", # Use a unique ID for the bot message
                        "text": lex_response_message,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                }
            ],
            # Optionally include session state for debugging/client-side use
            "sessionState": lex_response.get("sessionState", {})
        }

        return {
            "statusCode": 200,
            "body": json.dumps(formatted_response),
            "headers": HEADERS
        }

    except ValueError as e:
        # Handle client-side errors (e.g., bad request format)
        print(f"Client Error: {str(e)}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Bad Request: {str(e)}"}),
            "headers": HEADERS
        }

    except Exception as e:
        # Handle internal errors (e.g., Lex API failure, IAM issue)
        print(f"Internal Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error during Lex interaction."}),
            "headers": HEADERS
        }