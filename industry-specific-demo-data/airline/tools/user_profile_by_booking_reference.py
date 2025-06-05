#
# Copyright 2025 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#   http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
#

import os
import json
import logging
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

# Default responses
defaultResponse = {
    "status": "error",
    "response": "Sorry we couldn't locate you in our records with Booking Reference# {search_value}. Could you please check your details again?"
}

systemError = {
    "status": "error",
    "response": "We are currently unable to retrieve your booking. Please try again later."
}


def get_dynamodb_table_name():
    """Loads and returns the DynamoDB table name from the .env file."""
    table_name = os.getenv("DYNAMODB_TABLE_NAME")
    if not table_name:
        raise ValueError("DYNAMODB_TABLE_NAME not found in .env file")
    return table_name


def get_dynamodb_resource(session=None):
    """Returns a DynamoDB resource using the provided session or creates a new one."""
    return session.resource('dynamodb') if session else boto3.resource('dynamodb')


def search_by_booking_reference(booking_reference: str, retry: bool = False, session=None):
    """
    Search for booking records by booking reference with retry capability.
    
    Args:
        booking_reference: The user's booking reference
        retry: Whether this is a retry attempt
        session: Optional boto3 session to use
        
    Returns:
        Lookup result or error response
    """
    search_value = str(booking_reference).replace(" ", "").replace("-", "").replace(".", "")
    logger.info(f"Searching by booking_reference: {search_value}, retry: {retry}")
    
    try:
        table_name = get_dynamodb_table_name()
        index_name = f"{table_name}-index"

        # Create the boto3 client using the provided session or default
        dynamodb = get_dynamodb_resource(session)

        # Get the table
        table = dynamodb.Table(table_name)

        # Query by bookingReference using the GSI
        response = table.query(
            IndexName=index_name,
            KeyConditionExpression=Key('bookingReference').eq(search_value.upper())
        )

        logger.info(f"Query result: {json.dumps(response)}")

        if response['Count'] > 0:
            now = datetime.now()
            upcoming_flights = []

            for item in response['Items']:
                dep_str = f"{item['departureDate']} {item['departureTime']}"
                dep_datetime = datetime.strptime(dep_str, "%Y-%m-%d %H:%M")

                if dep_datetime > now:
                    upcoming_flights.append(item)

            sorted_flights = sorted(
                upcoming_flights,
                key=lambda x: (x['departureDate'], x['departureTime'])
            )

            result = {"status": "success", "response": sorted_flights}
            logger.info(f"Upcoming flights found: {json.dumps(result)}")
            return result

        logger.info(f"No booking records found for booking_reference: {search_value}")
        response_obj = defaultResponse.copy()
        response_obj["response"] = response_obj["response"].format(search_value=search_value)
        return response_obj

    except (ProfileNotFound, NoCredentialsError) as e:
        logger.error(f"AWS credential error: {str(e)}")
        return systemError

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(f"DynamoDB ClientError: {error_code} - {error_message}")
        
        # Handle expired token by creating a new session and retrying once
        if error_code == 'ExpiredTokenException' and not retry:
            logger.info("Retrying with refreshed session due to ExpiredTokenException")
            new_session = boto3.Session()
            return search_by_booking_reference(booking_reference, retry=True, session=new_session)
            
        return systemError

    except ConnectionError as e:
        logger.error(f"Network error: {str(e)}")
        return systemError

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return systemError


def main(booking_reference: str, session=None):
    """
    Search for booking records by booking reference.
    
    :param booking_reference: The user's booking reference
    :param session: Optional boto3 session to use
        
    :return: Lookup result or error response
    """
    logger.info(f"in main search by booking called with booking_reference: {booking_reference}")
    return search_by_booking_reference(booking_reference, session=session)


# For direct testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python user_profile_ByBooking.py <booking_reference>")
        sys.exit(1)
    
    booking_reference_arg = sys.argv[1]
    result = main(booking_reference_arg)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result and result.get("status") == "success" else 1)
