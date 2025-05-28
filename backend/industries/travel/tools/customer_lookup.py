#!/usr/bin/env python3

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

"""
@tool
name: customerLookup
description: Looks up customer information by booking reference, contact phone, or vehicle registration
parameters:
  - name: identifier
    type: string
    description: Booking reference, contact phone, or vehicle registration number provided by customer
    required: true
  - name: identifier_type
    type: string
    description: Type of identifier (booking_ref, contact_phone, vehicle_reg)
    required: true
"""

import os
import json
import logging
from boto3.dynamodb.conditions import Key, Attr
import boto3
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
    "response": "Sorry, we couldn't find any customer information with the provided details."
}

systemError = {
    "status": "error",
    "response": "We are currently unable to retrieve customer information. Please try again later."
}

def get_dynamodb_table_names():
    """Loads and returns the DynamoDB table names from the .env file."""
    bookings_table = os.getenv("DYNAMODB_BOOKINGS_TABLE", "thl_customer_bookings")
    vehicles_table = os.getenv("DYNAMODB_VEHICLES_TABLE", "thl_vehicle_information")
    return bookings_table, vehicles_table

def get_dynamodb_resource(session=None):
    """Returns a DynamoDB resource using the provided session or creates a new one."""
    return session.resource('dynamodb') if session else boto3.resource('dynamodb')

def lookup_customer(identifier: str, identifier_type: str, retry: bool = False, session=None):
    """
    Look up customer information with retry capability.
    
    Args:
        identifier: Booking reference, contact phone, or vehicle registration
        identifier_type: Type of identifier (booking_ref, contact_phone, vehicle_reg)
        retry: Whether this is a retry attempt
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with customer information
    """
    try:
        logger.info(f"Looking up customer with {identifier_type}: {identifier}, retry: {retry}")
        print(f"Looking up customer with {identifier_type}: {identifier}, retry: {retry}")
        # Get table names from environment
        bookings_table_name, vehicles_table_name = get_dynamodb_table_names()
        
        # Create the boto3 client using the provided session or default
        dynamodb = get_dynamodb_resource(session)
        
        # Get the tables
        bookings_table = dynamodb.Table(bookings_table_name)
        vehicles_table = dynamodb.Table(vehicles_table_name)
        bookings_table_index = bookings_table_name + "-index"
        customer_info = None
        vehicle_info = None
        
        # Look up by booking reference
        if identifier_type == 'contact_phone':
            response = bookings_table.query(
                KeyConditionExpression=Key('contact_phone').eq(identifier)
            )
            if response['Items']:
                customer_info = response['Items'][0]
                
                # Get vehicle information
                if 'vehicle_reg' in customer_info:
                    vehicle_response = vehicles_table.get_item(Key={'registration': customer_info['vehicle_reg']})
                    if 'Item' in vehicle_response:
                        vehicle_info = vehicle_response['Item']
        
        # Look up by contact phone
        elif identifier_type == 'booking_ref':
            response = bookings_table.query(
                IndexName=bookings_table_index,
                KeyConditionExpression=Key('booking_ref').eq(identifier)
            )
            if response['Items']:
                customer_info = response['Items'][0]
                
                # Get vehicle information
                if 'vehicle_reg' in customer_info:
                    vehicle_response = vehicles_table.get_item(Key={'registration': customer_info['vehicle_reg']})
                    if 'Item' in vehicle_response:
                        vehicle_info = vehicle_response['Item']
        
        # Look up by vehicle registration
        elif identifier_type == 'vehicle_reg':
            # First get vehicle info
            vehicle_response = vehicles_table.get_item(Key={'registration': identifier})
            if 'Item' in vehicle_response:
                vehicle_info = vehicle_response['Item']
                
                # Then find customer with this vehicle
                response = bookings_table.scan(
                    FilterExpression=Attr('vehicle_reg').eq(identifier)
                )
                if response['Items']:
                    customer_info = response['Items'][0]
        
        if customer_info:
            result = {
                "status": "success",
                "customer": customer_info,
                "vehicle": vehicle_info
            }
            logger.info(f"Customer found: {json.dumps(result)}")
            return result
        
        logger.info(f"No customer found with {identifier_type}: {identifier}")
        response_obj = defaultResponse.copy()
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
            return lookup_customer(identifier, identifier_type, retry=True, session=new_session)
            
        return systemError

    except ConnectionError as e:
        logger.error(f"Network error: {str(e)}")
        return systemError

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return systemError

def main(identifier: str, identifier_type: str, session=None):
    """
    Look up customer information.
    
    Args:
        identifier: Booking reference, contact phone, or vehicle registration
        identifier_type: Type of identifier (booking_ref, contact_phone, vehicle_reg)
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with customer information
    """
    logger.info(f"In main customer lookup called with {identifier_type}: {identifier}")
    return lookup_customer(identifier, identifier_type, session=session)

# For direct testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python customer_lookup.py <identifier_type> <identifier>")
        print("identifier_type can be: booking_ref, contact_phone, vehicle_reg")
        sys.exit(1)
    
    identifier_type_arg = sys.argv[1]
    identifier_arg = sys.argv[2]
    result = main(identifier_arg, identifier_type_arg)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result and result.get("status") == "success" else 1)
