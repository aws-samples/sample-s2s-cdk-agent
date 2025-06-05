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


import boto3
from boto3.dynamodb.conditions import Key
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Load environment variables from .env file
load_dotenv()

defaultResponse = {
    "status": "error",
    "response": "Sorry we couldn't locate you in our records with booking reference {search_value}. Could you please check your details again?"
}

systemError = {
    "status": "error",
    "response": "We are currently unable to retrieve your booking. Please try again later."
}

def get_dynamodb_table_name():
    table_name = os.getenv("DYNAMODB_TABLE_NAME")
    if not table_name:
        raise ValueError("DYNAMODB_TABLE_NAME not found in .env file")
    return table_name

def get_dynamodb_resource(session=None):
    return session.resource('dynamodb') if session else boto3.resource('dynamodb')

def submit_request(booking_reference: str, meal_type: str, retry: bool = False, session=None):
    meal_type = str(meal_type)
    booking_reference = str(booking_reference).replace(" ", "").replace("-", "").replace(".", "")
    logger.info(f"Processing request - , Meal Type: {meal_type}")

    try:
        table_name = get_dynamodb_table_name()
        index_name = f"{table_name}-index"
        dynamodb = get_dynamodb_resource(session)
        table = dynamodb.Table(table_name)

        response = table.query(
            IndexName=index_name,
            KeyConditionExpression=Key('bookingReference').eq(booking_reference.upper())
        )

        items = response.get('Items', [])

        if not items:
            logger.info(f"No booking records found for booking reference number")
            response_obj = defaultResponse.copy()
            response_obj["response"] = response_obj["response"].format(search_value=booking_reference)
            return response_obj

        for item in items:
            departure_date_str = item.get('departureDate')
            departure_time_str = item.get('departureTime')

            if not departure_date_str or not departure_time_str:
                logger.warning(f"Departure date/time missing for requested booking")
                return systemError

            try:
                combined_datetime_str = f"{departure_date_str} {departure_time_str}"
                departure_time = datetime.strptime(combined_datetime_str, "%Y-%m-%d %H:%M")
                departure_time = departure_time.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.error(f"Invalid departure date/time format: {combined_datetime_str}")
                return systemError

            current_time = datetime.now(timezone.utc)
            if departure_time - current_time < timedelta(hours=24):
                logger.info(f"Meal request rejected: Less than 24 hours to departure")
                return {
                    "status": "error",
                    "response": "Meal requests must be made at least 24 hours before departure. Please contact support."
                }

            pk = item.get('frequentFlyerNumber')
            sk = item.get('bookingReference')

            update_response = table.update_item(
                Key={
                    'frequentFlyerNumber': pk,
                    'bookingReference': sk
                },
                UpdateExpression="SET mealSelected = :meal",
                ExpressionAttributeValues={':meal': meal_type},
                ReturnValues="ALL_NEW"
            )

            updated_item = update_response.get('Attributes', {})
            return updated_item

    except (ProfileNotFound, NoCredentialsError) as e:
        logger.error(f"AWS credential error: {str(e)}")
        return systemError

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(f"DynamoDB ClientError: {error_code} - {error_message}")

        if error_code == 'ExpiredTokenException' and not retry:
            logger.info("Retrying with refreshed session due to ExpiredTokenException")
            new_session = boto3.Session()
            return submit_request(booking_reference, meal_type, retry=True, session=new_session)

        return systemError

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return systemError

def main(booking_reference: str, meal_type: str, session=None):
    logger.info(f"Received booking request with meal type: {meal_type}")
    result = submit_request(booking_reference, meal_type, session=session)
    logger.info(f"Result: {json.dumps(result)}")
    return result

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <booking_reference> <meal_type>")
        sys.exit(1)

    booking_reference = sys.argv[1]
    meal_type = sys.argv[2]
    result = main(booking_reference, meal_type)

    sys.exit(0 if result and result.get("status", "") != "error" else 1)
