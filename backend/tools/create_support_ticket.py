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

import boto3
import logging
import os
import json
import random
from datetime import datetime
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

# Default error response
systemError = {
    "status": "error",
    "message": "We are currently unable to create a support ticket. Please try again later."
}

def get_dynamodb_table_name():
    """Loads and returns the DynamoDB table name from the .env file."""
    table_name = os.getenv("DYNAMODB_TABLE_NAME")
    if not table_name:
        raise ValueError("DYNAMODB_TABLE_NAME not found in .env file")
    return table_name

def get_dynamodb_resource(session=None):
    """Returns a DynamoDB resource using the provided session or creates a new one."""
    # Get region from environment variable or use the session's region

    if session:
        return session.resource('dynamodb')
    else:
        # If no session provided, create resource with region
        return boto3.resource('dynamodb')

def create_ticket(issue_summary, booking_reference, retry=False, session=None):
    """
    Creates a support ticket by logging it in DynamoDB with retry capability.
    
    Args:
        issue_summary (str): A summary of the issue raised by the user
        booking_reference (str): The booking reference to associate with the support ticket
        retry (bool): Whether this is a retry attempt
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with status and message
    """
    try:
        # Format booking reference (remove spaces, dashes, etc.)
        booking_reference = str(booking_reference).replace(" ", "").replace("-", "").replace(".", "").upper()
        logger.info(f"Creating support ticket for provided booking reference, retry: {retry}")
        
        # Initialize DynamoDB client with the provided session or default
        dynamodb = get_dynamodb_resource(session)
        
        # Get table name from environment
        table_name = get_dynamodb_table_name()
        table = dynamodb.Table(table_name)
        
        # Current timestamp
        timestamp = datetime.now().isoformat()
        
        # Generate a unique ticket ID (6-digit random number)
        ticket_id = str(random.randint(100000, 999999))
        
        # Create ticket object
        ticket = {
            "id": ticket_id,
            "timestamp": timestamp,
            "issue_summary": issue_summary,
            "status": "open"
        }
            
        # First, get the current item to check if it exists
        try:
            response = table.query(
                IndexName=f"{table_name}-index",
                KeyConditionExpression=Key('bookingReference').eq(booking_reference)
            )
            
            if response['Count'] > 0:
                # Item exists, update it
                item = response['Items'][0]
                
                # Get the primary key values
                pk = item.get('frequentFlyerNumber') or ""
                sk = item.get('bookingReference') or ""
                
                # Check if support_tickets already exists
                expression_attr_values = {
                    ':t': [ticket]
                }
                
                if 'support_tickets' in item:
                    update_expression = "SET support_tickets = list_append(support_tickets, :t)"
                else:
                    update_expression = "SET support_tickets = :t"
                
                # Update the item
                update_response = table.update_item(
                    Key={
                        'frequentFlyerNumber': pk,
                        'bookingReference': sk
                    },
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attr_values,
                    ReturnValues="UPDATED_NEW"
                )
                
                # logger.info(f"Support ticket added to existing record: {json.dumps(update_response)}")
            else:
                logger.error(f"No booking found with provided booking reference")
                return {
                    "status": "error",
                    "message": f"No booking found with provided booking reference"
                }
                
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            logger.error(f"DynamoDB ClientError: {error_code} - {error_message}")
            
            # Handle expired token by creating a new session and retrying once
            if error_code == 'ExpiredTokenException' and not retry:
                logger.info("Retrying with refreshed session due to ExpiredTokenException")
                new_session = boto3.Session()
                return create_ticket(issue_summary, booking_reference, retry=True, session=new_session)
                
            return systemError
            
        except Exception as e:
            logger.error(f"Error updating DynamoDB: {str(e)}")
            raise e
        
        return {
            "status": "success",
            "message": "Support ticket created successfully",
            "ticket_id": ticket_id
        }
        
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
            return create_ticket(issue_summary, booking_reference, retry=True, session=new_session)
            
        return systemError
        
    except Exception as e:
        logger.error(f"Error creating support ticket: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to create support ticket: {str(e)}"
        }

def main(issue_summary, booking_reference, session=None):
    """
    Creates a support ticket by logging it in DynamoDB.
    
    Args:
        issue_summary (str): A summary of the issue raised by the user
        booking_reference (str): The booking reference to associate with the support ticket
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with status and message
    """
    logger.info(f"Creating support ticket with summary: '{issue_summary}' for the provided booking reference")
    return create_ticket(issue_summary, booking_reference, session=session)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python create_support_ticket.py <booking_reference_number> <issue_summary>")
        sys.exit(1)
    
    booking_referece = sys.argv[1]
    issue_summary = sys.argv[2]
    result = main(issue_summary, booking_referece)
    # print(json.dumps(result, indent=2))
    sys.exit(0 if result and result.get("status") == "success" else 1)


