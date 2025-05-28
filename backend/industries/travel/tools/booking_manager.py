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
name: bookingManager
description: Manages bookings - creates, modifies, or cancels accommodation bookings
parameters:
  - name: action
    type: string
    description: Action to perform (create, modify, cancel)
    required: true
  - name: booking_ref
    type: string
    description: Booking reference for modifications or cancellations
    required: false
  - name: customer_name
    type: string
    description: Customer's full name
    required: false
  - name: contact_phone
    type: string
    description: Customer's contact phone number
    required: false
  - name: customer_booking_ref
    type: string
    description: Customer's THL booking reference
    required: false
  - name: accommodation_id
    type: string
    description: ID of the accommodation to book
    required: false
  - name: trip_start
    type: string
    description: Trip start date (YYYY-MM-DD)
    required: false
  - name: trip_end
    type: string
    description: Trip end date (YYYY-MM-DD)
    required: false
  - name: site_type
    type: string
    description: Type of site (powered, unpowered, cabin)
    required: false
  - name: vehicle_reg
    type: string
    description: Vehicle registration number
    required: false
  - name: num_guests
    type: integer
    description: Number of guests for the booking
    required: false
  - name: special_requests
    type: string
    description: Any special requests for the booking
    required: false
"""

import os
import boto3
import logging
import uuid
import time
import json
import random
import string
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
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
    "response": "Sorry, we couldn't process your booking request. Please check your details and try again."
}

systemError = {
    "status": "error",
    "response": "We are currently unable to process your booking request. Please try again later."
}

def generate_booking_reference():
    """Generate a unique booking reference."""
    # Format: THL-YYYYMMDD-XXXXX where X is alphanumeric
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"THL-{date_part}-{random_part}"

def get_dynamodb_table_names():
    """Loads and returns the DynamoDB table names from the .env file."""
    bookings_table = os.getenv("DYNAMODB_BOOKINGS_TABLE", "thl_customer_bookings")
    accommodation_table = os.getenv("DYNAMODB_ACCOMMODATION_TABLE", "thl_accommodation_options")
    return bookings_table, accommodation_table

def get_dynamodb_resource(session=None):
    """Returns a DynamoDB resource using the provided session or creates a new one."""
    return session.resource('dynamodb') if session else boto3.resource('dynamodb')

def get_accommodation_details(accommodation_id, accommodation_table):
    """
    Fetch accommodation details from the accommodation table.
    
    Args:
        accommodation_id: ID of the accommodation to fetch
        accommodation_table: DynamoDB table for accommodations
        
    Returns:
        dict: Accommodation details including name and location
    """
    try:
        response = accommodation_table.get_item(Key={'id': accommodation_id})
        if 'Item' not in response:
            return None
        
        accommodation = response['Item']
        return {
            'name': accommodation.get('name', 'Unknown Accommodation'),
            'location': accommodation.get('location', 'Unknown Location')
        }
    except ClientError as e:
        logger.error(f"Error fetching accommodation details: {str(e)}")
        return None

def create_booking(contact_phone, accommodation_id, trip_start, trip_end, customer_name=None, 
                  site_type=None, vehicle_reg=None, num_guests=None, special_requests=None, 
                  customer_booking_ref=None, session=None):
    """
    Create a new booking with the required fields.
    
    Args:
        contact_phone: Customer's contact phone number (required)
        accommodation_id: ID of the accommodation to book (required)
        trip_start: Trip start date in YYYY-MM-DD format (required)
        trip_end: Trip end date in YYYY-MM-DD format (required)
        customer_name: Customer's full name (optional)
        site_type: Type of site (powered, unpowered, cabin) (optional)
        vehicle_reg: Vehicle registration number (optional)
        num_guests: Number of guests for the booking (optional)
        special_requests: Any special requests for the booking (optional)
        customer_booking_ref: Customer's THL booking reference (optional)
        session: Optional boto3 session to use
        
    Returns:
        dict: Result of the booking creation operation
    """
    try:
        logger.info(f"Creating new booking: contact_phone={contact_phone}, accommodation_id={accommodation_id}")
        logger.info(f"Trip dates: {trip_start} to {trip_end}")
        
        # Validate required fields
        if not all([contact_phone, accommodation_id, trip_start, trip_end]):
            missing_fields = []
            if not contact_phone: missing_fields.append("contact_phone")
            if not accommodation_id: missing_fields.append("accommodation_id")
            if not trip_start: missing_fields.append("trip_start")
            if not trip_end: missing_fields.append("trip_end")
            
            return {
                "status": "error",
                "response": f"Missing required fields: {', '.join(missing_fields)}"
            }
        
        # Get table names from environment
        bookings_table_name, accommodation_table_name = get_dynamodb_table_names()
        
        # Create the boto3 client using the provided session or default
        dynamodb = get_dynamodb_resource(session)
        
        # Get the tables
        bookings_table = dynamodb.Table(bookings_table_name)
        accommodation_table = dynamodb.Table(accommodation_table_name)
        
        # Fetch accommodation details
        accommodation_details = get_accommodation_details(accommodation_id, accommodation_table)
        if not accommodation_details:
            return {
                "status": "error",
                "response": f"Accommodation with ID {accommodation_id} not found"
            }
        
        # Generate a unique booking reference
        booking_ref = generate_booking_reference()
        
        # Create booking item for DynamoDB
        booking_item = {
            'booking_ref': booking_ref,
            'contact_phone': contact_phone,
            'accommodation_id': accommodation_id,
            'accommodation_name': accommodation_details['name'],
            'accommodation_location': accommodation_details['location'],
            'trip_start': trip_start,
            'trip_end': trip_end,
            'status': 'confirmed',
            'created_at': datetime.now().isoformat()
        }
        
        # Add optional fields if provided
        if customer_name:
            booking_item['customer_name'] = customer_name
            
        if site_type:
            booking_item['site_type'] = site_type
            
        if vehicle_reg:
            booking_item['vehicle_reg'] = vehicle_reg
            
        if customer_booking_ref:
            booking_item['customer_booking_ref'] = customer_booking_ref
            
        if num_guests:
            booking_item['num_guests'] = num_guests
            
        if special_requests:
            booking_item['special_requests'] = special_requests
        
        # Save the booking to DynamoDB
        bookings_table.put_item(Item=booking_item)
        
        return {
            "status": "success",
            "response": {
                "booking_ref": booking_ref,
                "message": "Booking created successfully",
                "details": booking_item
            }
        }
    
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(f"DynamoDB ClientError: {error_code} - {error_message}")
        return systemError
            
    except Exception as e:
        logger.error(f"Unexpected error creating booking: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return systemError

def manage_booking(action: str, booking_ref: str = None, customer_name: str = None, 
                  contact_phone: str = None, customer_booking_ref: str = None, 
                  accommodation_id: str = None, trip_start: str = None, 
                  trip_end: str = None, site_type: str = None, vehicle_reg: str = None,
                  num_guests: int = None, special_requests: str = None,
                  retry: bool = False, session=None):
    """
    Manage accommodation bookings with retry capability.
    
    Args:
        action: Action to perform (create, modify, cancel)
        booking_ref: Booking reference for modifications or cancellations
        customer_name: Customer's full name
        contact_phone: Customer's contact phone number
        customer_booking_ref: Customer's THL booking reference
        accommodation_id: ID of the accommodation to book
        trip_start: Trip start date (YYYY-MM-DD)
        trip_end: Trip end date (YYYY-MM-DD)
        site_type: Type of site (powered, unpowered, cabin)
        vehicle_reg: Vehicle registration number
        num_guests: Number of guests for the booking
        special_requests: Any special requests for the booking
        retry: Whether this is a retry attempt
        session: Optional boto3 session to use
        
    Returns:
        dict: Result of the booking operation
    """
    try:
        logger.info(f"Managing booking with action: {action}, retry: {retry}")
        
        if action == "create":
            return create_booking(
                contact_phone=contact_phone,
                accommodation_id=accommodation_id,
                trip_start=trip_start,
                trip_end=trip_end,
                customer_name=customer_name,
                site_type=site_type,
                vehicle_reg=vehicle_reg,
                num_guests=num_guests,
                special_requests=special_requests,
                customer_booking_ref=customer_booking_ref,
                session=session
            )
            
        elif action == "cancel":
            if not booking_ref:
                return {
                    "status": "error",
                    "response": "Booking reference required for cancellation"
                }
            
            # Implementation for cancel action would go here
            return {
                "status": "error",
                "response": "Cancellation feature not yet implemented"
            }
            
        elif action == "modify":
            if not booking_ref:
                return {
                    "status": "error",
                    "response": "Booking reference required for modification"
                }
            
            # Implementation for modify action would go here
            return {
                "status": "error",
                "response": "Modification feature not yet implemented"
            }
            
        else:
            return {
                "status": "error",
                "response": f"Invalid action: {action}. Must be one of: create, modify, cancel"
            }
    
    except Exception as e:
        logger.error(f"Error in manage_booking: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return systemError

def main(action: str, booking_ref: str = None, customer_name: str = None, 
         contact_phone: str = None, customer_booking_ref: str = None, 
         accommodation_id: str = None, trip_start: str = None, 
         trip_end: str = None, site_type: str = None, vehicle_reg: str = None,
         num_guests: int = None, special_requests: str = None, session=None):
    """
    Manage accommodation bookings.
    
    Args:
        action: Action to perform (create, modify, cancel)
        booking_ref: Booking reference for modifications or cancellations
        customer_name: Customer's full name
        contact_phone: Customer's contact phone number
        customer_booking_ref: Customer's THL booking reference
        accommodation_id: ID of the accommodation to book
        trip_start: Trip start date (YYYY-MM-DD)
        trip_end: Trip end date (YYYY-MM-DD)
        site_type: Type of site (powered, unpowered, cabin)
        vehicle_reg: Vehicle registration number
        num_guests: Number of guests for the booking
        special_requests: Any special requests for the booking
        session: Optional boto3 session to use
        
    Returns:
        dict: Result of the booking operation
    """
    logger.info(f"In main booking manager called with action: {action}")
    try:
        return manage_booking(
            action=action, 
            booking_ref=booking_ref, 
            customer_name=customer_name, 
            contact_phone=contact_phone, 
            customer_booking_ref=customer_booking_ref, 
            accommodation_id=accommodation_id, 
            trip_start=trip_start, 
            trip_end=trip_end, 
            site_type=site_type, 
            vehicle_reg=vehicle_reg,
            num_guests=num_guests,
            special_requests=special_requests,
            session=session
        )
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return systemError

# For direct testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python booking_manager.py <action> [parameters]")
        print("Actions: create, modify, cancel")
        print("For create: python booking_manager.py create <contact_phone> <accommodation_id> <trip_start> <trip_end> [customer_name] [site_type] [vehicle_reg] [num_guests] [special_requests] [customer_booking_ref]")
        print("For modify: python booking_manager.py modify <booking_ref> [parameters to modify]")
        print("For cancel: python booking_manager.py cancel <booking_ref>")
        sys.exit(1)
    
    action_arg = sys.argv[1]
    
    try:
        if action_arg == "create" and len(sys.argv) >= 5:
            print(f"Processing create action with {len(sys.argv)} arguments")
            kwargs = {
                "action": action_arg,
                "contact_phone": sys.argv[2],
                "accommodation_id": sys.argv[3],
                "trip_start": sys.argv[4],
                "trip_end": sys.argv[5] if len(sys.argv) > 5 else None
            }
            
            if len(sys.argv) > 6:
                kwargs["customer_name"] = sys.argv[6]
            if len(sys.argv) > 7:
                kwargs["site_type"] = sys.argv[7]
            if len(sys.argv) > 8:
                kwargs["vehicle_reg"] = sys.argv[8]
            if len(sys.argv) > 9:
                kwargs["num_guests"] = int(sys.argv[9])
            if len(sys.argv) > 10:
                kwargs["special_requests"] = sys.argv[10]
            if len(sys.argv) > 11:
                kwargs["customer_booking_ref"] = sys.argv[11]
                
            # Remove action from kwargs as it's passed separately
            action = kwargs.pop("action")
            result = main(action, **kwargs)
        elif action_arg == "modify" and len(sys.argv) >= 3:
            # Implementation for modify command line arguments would go here
            print("Modify action not yet implemented")
            sys.exit(1)
        elif action_arg == "cancel" and len(sys.argv) >= 3:
            # Implementation for cancel command line arguments would go here
            print("Cancel action not yet implemented")
            sys.exit(1)
        else:
            print("Invalid arguments")
            sys.exit(1)
    except Exception as e:
        import traceback
        print(f"Error in command line processing: {str(e)}")
        print(traceback.format_exc())
        result = systemError
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result and result.get("status") == "success" else 1)
