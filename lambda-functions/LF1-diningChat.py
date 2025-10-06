import json
import os
import boto3
import re
# Removed unnecessary imports: datetime, dateutil.parser

# --- AWS CLIENT INITIALIZATION ---
# NOTE: Ensure SQS_QUEUE_URL is set as an environment variable in Lambda configuration
# Example: SQS_QUEUE_URL = https://sqs.us-east-1.amazonaws.com/123456789012/DiningRequestsQueue
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL')
DYNAMO_TABLE_NAME = "UserSearchState"

# Initialize AWS clients (region should match your bot and table region)
REGION = 'us-east-1' 
sqs = boto3.client('sqs', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
user_state_table = dynamodb.Table(DYNAMO_TABLE_NAME)

# --- HELPER FUNCTIONS ---

def validate(slots):
    """
    Validates the collected slots.
    Note: Lex V2 slots are dictionaries, use .get() for safety.
    """
    valid_cities = ['new york']
    valid_cuisines = ['chinese', 'indian', 'italian', 'mexican', 'thai']

    # 1. Location Validation
    location_slot = slots.get('Location')
    if location_slot and location_slot.get('value'):
        city = location_slot['value']['interpretedValue'].lower()
        if city not in valid_cities:
            return {
                'isValid': False,
                'violatedSlot': 'Location',
                'message': f"We do not have suggestions in {location_slot['value']['originalValue']} currently. Please choose New York to proceed further."
            }
    
    # 2. Cuisine Validation
    cuisine_slot = slots.get('Cuisine')
    if cuisine_slot and cuisine_slot.get('value'):
        cuisine = cuisine_slot['value']['interpretedValue'].lower()
        if cuisine not in valid_cuisines:
            return {
                'isValid': False,
                'violatedSlot': 'Cuisine',
                'message': f"We do not have suggestions for {cuisine_slot['value']['originalValue']} restaurants currently. Please choose from {', '.join(valid_cuisines)}."
            }

    # Checks for presence of all required slots (will be redundant if Lex config is correct)
    for slot_name in ['Location', 'Cuisine', 'DiningTime', 'NumPeople', 'Email']:
        if not slots.get(slot_name) or not slots[slot_name].get('value'):
            # This case means the DialogCodeHook was called but a slot is missing. 
            # We return True here and rely on Lex to prompt for the missing slot 
            # (unless it's validation logic we want to override).
            pass 

    return {'isValid': True}


def store_last_search(user_id, location, cuisine, dining_time, num_people, email):
    """Store the user's last search in DynamoDB."""
    try:
        user_state_table.put_item(
            Item={
                'UserId': user_id,
                'LastLocation': location,
                'LastCuisine': cuisine,
                'DiningTime': dining_time,
                'NumPeople': num_people,
                'Email': email
            }
        )
        print(f"User state stored for user_id: {user_id}")
    except Exception as e:
        print(f"Error storing user state: {e}")


def get_last_search(user_id):
    """Retrieve the user's last search from DynamoDB."""
    try:
        response = user_state_table.get_item(Key={'UserId': user_id})
        return response.get('Item')
    except Exception as e:
        print(f"Error retrieving user state: {e}")
        return None


def push_to_sqs(user_id, location, cuisine, dining_time, num_people, email, state):
    """Send the user's search details to SQS."""
    if not SQS_QUEUE_URL:
        raise EnvironmentError("SQS_QUEUE_URL is not set as an environment variable.")

    message = {
        'Location': location,
        'Cuisine': cuisine,
        'DiningTime': dining_time,
        'NumPeople': num_people,
        'Email': email,
        'SessionID': user_id,
        'State': state
    }

    try:
        response = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(message)
        )
        print(f"Message sent to SQS: {response}")
    except Exception as e:
        print(f"Error sending message to SQS: {e}")
        raise e


def elicit_slot(event, slot_name, message):
    """Tells Lex to ask the user for a specific slot value."""
    # Ensure current slots and session attributes are passed back
    session_attributes = event['sessionState'].get('sessionAttributes', {})
    
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': slot_name
            },
            'intent': event['sessionState']['intent'],
            'sessionAttributes': session_attributes
        },
        'messages': [{
            'contentType': 'PlainText',
            'content': message
        }]
    }

def delegate(event, slots, session_attributes=None):
    """Tells Lex to continue the conversation flow (collecting remaining slots)."""
    intent = event['sessionState']['intent']
    intent['slots'] = slots
    
    response = {
        "sessionState": {
            "dialogAction": {
                "type": "Delegate"
            },
            "intent": intent,
        }
    }
    
    if session_attributes:
        response['sessionState']['sessionAttributes'] = session_attributes
        
    return response

def close_session(event, message, fulfillment_state='Fulfilled'):
    """Close the session with a fulfillment message."""
    # Ensure any final session attributes are passed back
    session_attributes = event['sessionState'].get('sessionAttributes', {})

    return {
        'sessionState': {
            'dialogAction': {
                'type': 'Close'
            },
            'intent': {
                'name': event['sessionState']['intent']['name'],
                'state': fulfillment_state
            },
            'sessionAttributes': session_attributes
        },
        'messages': [{
            'contentType': 'PlainText',
            'content': message
        }]
    }


# --- INTENT HANDLER LOGIC ---

def handle_dining_suggestions_intent(event, user_id, intent_name, slots):

    # Get state variables
    confirmation_state = event['sessionState']['intent']['confirmationState']
    session_attributes = event['sessionState'].get('sessionAttributes', {})
    denied_state = session_attributes.get('deniedState', 'false') == 'true'
    last_search = get_last_search(user_id)

    # --- DIALOG CODE HOOK (Validation, Confirmation) ---
    if event['invocationSource'] == 'DialogCodeHook':
        
        # PHASE 1: PRE-CONFIRMATION CHECK (Ask to reuse past search)
        # This checks if we have a last search, confirmation hasn't started, and user hasn't denied the previous offer.
        if last_search and confirmation_state == "None" and not denied_state:
            location_slot_value = slots.get('Location')
            
            # Check if the user's current or implied location matches the last search location
            if location_slot_value and location_slot_value['value']['interpretedValue'] == last_search['LastLocation']:
                
                # Ask the user if they want to reuse the stored preference
                session_attributes['deniedState'] = 'false' # Reset for this conversation branch
                return {
                    'sessionState': {
                        'dialogAction': {'type': 'ConfirmIntent'},
                        'intent': event['sessionState']['intent'],
                        'sessionAttributes': session_attributes,
                        'messages': [{
                            'contentType': 'PlainText',
                            'content': f"I have your previous preferences: {last_search['LastCuisine']} food in {last_search['LastLocation']} at {last_search['DiningTime']}. Do you want to use them?"
                        }]
                    }
                }
        
        # PHASE 2: VALIDATION / DENIAL / DELEGATION (If no last search, or denied, or after validation)
        
        # This path is taken if:
        # 1. No last search exists.
        # 2. User denied the confirmation (confirmation_state == "Denied").
        # 3. We have explicitly set denied_state = True from a previous turn.
        
        if confirmation_state == "Denied" or not last_search or denied_state:
            
            # Set state attribute if denial happened, or if we are continuing a denied flow.
            if confirmation_state == "Denied" or denied_state:
                session_attributes['deniedState'] = 'true'
            else:
                # If no last search, we don't need a denied state.
                session_attributes['deniedState'] = 'false'

            validation_result = validate(slots)

            if not validation_result['isValid']:
                # Validation failed, elicit the specific slot
                message = validation_result.get('message', "Please provide a valid value.")
                return elicit_slot(event, validation_result['violatedSlot'], message)
            
            else:
                # Validation passed, allow Lex to continue slot collection or proceed to fulfillment
                return delegate(event, slots, session_attributes)


        # PHASE 3: CONFIRMED (User said YES to previous search)
        elif confirmation_state == "Confirmed":
            
            # Load slots from DynamoDB and populate the current intent slots
            if last_search:
                # Populate all required slots with the saved values. Must include originalValue/interpretedValue structure.
                slots['Location'] = {"value": {"interpretedValue": last_search["LastLocation"], "originalValue": last_search["LastLocation"]}}
                slots['Cuisine'] = {"value": {"interpretedValue": last_search["LastCuisine"], "originalValue": last_search["LastCuisine"]}}
                slots['DiningTime'] = {"value": {"interpretedValue": last_search["DiningTime"], "originalValue": last_search["DiningTime"]}}
                slots['NumPeople'] = {"value": {"interpretedValue": last_search["NumPeople"], "originalValue": last_search["NumPeople"]}}
                slots['Email'] = {"value": {"interpretedValue": last_search["Email"], "originalValue": last_search["Email"]}}

            # IMPORTANT: Delegate back to Lex. Lex sees all slots are filled and calls FulfillmentCodeHook immediately.
            session_attributes['deniedState'] = 'false' # Reset state before fulfillment
            return delegate(event, slots, session_attributes)
            
        # Default DialogCodeHook return should be Delegate to allow Lex to continue slot collection
        return delegate(event, slots, session_attributes)


    # --- FULFILLMENT CODE HOOK (Final Action) ---
    elif event['invocationSource'] == 'FulfillmentCodeHook':

        # Extract all collected data from the slots
        try:
            location = slots['Location']['value']['interpretedValue']
            cuisine = slots['Cuisine']['value']['interpretedValue']
            dining_time = slots['DiningTime']['value']['interpretedValue']
            num_people = slots['NumPeople']['value']['interpretedValue']
            email = slots['Email']['value']['interpretedValue']
        except KeyError:
            # Failsafe if a required slot somehow didn't get collected (shouldn't happen with correct config)
            return close_session(event, "Sorry, I am missing some details to complete your request.", 'Failed')

        # Determine the state for SQS message
        if confirmation_state == 'Confirmed':
            state = 'old'
        else:
            # User provided new details directly, or after denial/no previous data
            state = 'new'
            store_last_search(user_id, location, cuisine, dining_time, num_people, email)

        # Push the search details to SQS
        try:
            push_to_sqs(user_id, location, cuisine, dining_time, num_people, email, state)
            
            # Clear the denied state from the session attributes for future conversations
            session_attributes['deniedState'] = 'false'
            
            return close_session(event, f"Got it! We received your request for {cuisine} in {location} and will send the recommendations to {email} shortly.")
        except Exception as e:
            print(f"SQS Error during fulfillment: {e}")
            return close_session(event, "Sorry, I couldn't process your request to send the email at this time.", 'Failed')

    # Failsafe for unexpected invocation source
    return close_session(event, "I encountered an unexpected issue.", 'Failed')


# --- MAIN HANDLER ---

def lambda_handler(event, context):
    
    # Enable CORS for testing in browser (optional, but good practice)
    headers = {'Access-Control-Allow-Origin': '*'}
    
    # Check for core Lex V2 structure
    if 'sessionState' not in event or 'intent' not in event['sessionState']:
        print("ERROR: Invalid Lex V2 event structure.")
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"message": "Invalid Lex V2 event structure."})
        }
    
    intent_name = event['sessionState']['intent']['name']
    slots = event['sessionState']['intent']['slots']
    user_id = event['sessionId']

    print(f"Processing Intent: {intent_name}, User: {user_id}")

    # Handle GreetingIntent
    if intent_name == "GreetingIntent":
        return close_session(event, 'Hi there, how can I help you today?')

    # Handle ThankYouIntent
    elif intent_name == "ThankYouIntent":
        return close_session(event, "You're welcome! Let me know if you need anything else")

    # Handle DiningSuggestionIntent
    elif intent_name == "DiningSuggestionIntent":
        return handle_dining_suggestions_intent(event, user_id, intent_name, slots)
    
    # Default/Fallback
    return close_session(event, 'Sorry, I did not understand your request.', 'Failed')