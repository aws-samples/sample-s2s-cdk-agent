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

# tools.py
from typing import Annotated, Union, Optional
from pydantic import Field
from mcp_server import mcp_server
import logging
from . import customer_lookup
from . import booking_manager
from . import accommodation_finder
from . import appliance_troubleshooting

logger = logging.getLogger(__name__)

# Customer Lookup Tool
@mcp_server.tool(
    name="customerLookup",
    description="Search for customer information using their identifier (email, phone, or customer ID)"
)
async def customer_lookup_tool(
    identifier: Annotated[str, Field(description="the customer identifier (email, phone number, or customer ID)")],
    identifier_type: Annotated[str, Field(description="the type of identifier being used (email, phone, or customer_id)")]
) -> dict:
    """Look up customer information using their identifier"""
    try:
        logger.info(f"Customer lookup with {identifier_type}: {identifier}")
        results = customer_lookup.main(identifier, identifier_type)
        return results
    except Exception as e:
        logger.error(f"Error in customer lookup: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}

# Booking Manager Tool
@mcp_server.tool(
    name="bookingManager",
    description="Manage customer bookings - create, modify, cancel, or retrieve booking information"
)
async def booking_manager_tool(
    action: Annotated[str, Field(description="the action to perform (create, modify, cancel, get)")],
    booking_ref: Annotated[Optional[str], Field(description="the booking reference number")] = None,
    customer_name: Annotated[Optional[str], Field(description="the customer's full name")] = None,
    contact_phone: Annotated[Optional[str], Field(description="the customer's contact phone number")] = None,
    customer_booking_ref: Annotated[Optional[str], Field(description="the customer's booking reference")] = None,
    accommodation_id: Annotated[Optional[str], Field(description="the accommodation ID")] = None,
    trip_start: Annotated[Optional[str], Field(description="the trip start date (YYYY-MM-DD)")] = None
) -> dict:
    """Manage customer travel bookings"""
    try:
        logger.info(f"Booking manager action: {action} for booking ref: {booking_ref}")
        results = booking_manager.main(
            action=action,
            booking_ref=booking_ref,
            customer_name=customer_name,
            contact_phone=contact_phone,
            customer_booking_ref=customer_booking_ref,
            accommodation_id=accommodation_id,
            trip_start=trip_start
        )
        return results
    except Exception as e:
        logger.error(f"Error in booking manager: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}

# Accommodation Finder Tool
@mcp_server.tool(
    name="accommodationFinder",
    description="Find accommodation options based on location and preferences"
)
async def accommodation_finder_tool(
    location: Annotated[str, Field(description="the location to search for accommodations")],
    family_friendly: Annotated[Optional[bool], Field(description="filter for family-friendly accommodations")] = None,
    powered_site: Annotated[Optional[bool], Field(description="filter for accommodations with powered sites")] = None,
    pet_friendly: Annotated[Optional[bool], Field(description="filter for pet-friendly accommodations")] = None,
    max_distance: Annotated[Optional[float], Field(description="maximum distance from location in kilometers")] = 50
) -> dict:
    """Find accommodation options based on location and preferences"""
    try:
        logger.info(f"Accommodation search for location: {location}")
        results = accommodation_finder.main(
            location=location,
            family_friendly=family_friendly,
            powered_site=powered_site,
            pet_friendly=pet_friendly,
            max_distance=max_distance
        )
        return results
    except Exception as e:
        logger.error(f"Error in accommodation finder: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}

# Appliance Troubleshooting Tool
@mcp_server.tool(
    name="applianceTroubleshooting",
    description="Provide troubleshooting steps for campervan or RV appliance issues"
)
async def appliance_troubleshooting_tool(
    appliance_type: Annotated[str, Field(description="the type of appliance having issues (e.g., fridge, heater, stove)")],
    issue_description: Annotated[str, Field(description="description of the issue being experienced")],
    vehicle_model: Annotated[Optional[str], Field(description="the vehicle model if known")] = None
) -> dict:
    """Provide troubleshooting steps for campervan or RV appliance issues"""
    try:
        logger.info(f"Appliance troubleshooting for {appliance_type}: {issue_description}")
        results = appliance_troubleshooting.main(
            appliance_type=appliance_type,
            issue_description=issue_description,
            vehicle_model=vehicle_model
        )
        return results
    except Exception as e:
        logger.error(f"Error in appliance troubleshooting: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}
