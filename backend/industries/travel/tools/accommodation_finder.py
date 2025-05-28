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
name: accommodationFinder
description: Finds available accommodation options near a location
parameters:
  - name: location
    type: string
    description: Location to search near
    required: true
  - name: family_friendly
    type: boolean
    description: Whether accommodation should be family-friendly
    required: false
  - name: powered_site
    type: boolean
    description: Whether powered sites are required
    required: false
  - name: pet_friendly
    type: boolean
    description: Whether accommodation should be pet-friendly
    required: false
  - name: max_distance
    type: number
    description: Maximum distance in kilometers to search (default is 50km)
    required: false
"""

import os
import boto3
import logging
import math
import json
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from dotenv import load_dotenv

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

# Default responses
defaultResponse = {
    "status": "error",
    "response": "Sorry, we couldn't find any accommodation options matching your criteria."
}

systemError = {
    "status": "error",
    "response": "We are currently unable to search for accommodation. Please try again later."
}

# Dictionary mapping common New Zealand locations to their approximate coordinates
# This would be replaced with a proper geocoding service in production
LOCATION_COORDINATES = {
    "auckland": (-36.8509, 174.7645),
    "wellington": (-41.2865, 174.7762),
    "christchurch": (-43.5321, 172.6362),
    "queenstown": (-45.0302, 168.6616),
    "rotorua": (-38.1368, 176.2497),
    "taupo": (-38.6857, 176.0702),
    "wanaka": (-44.7032, 169.1304),
    "napier": (-39.4928, 176.9120),
    "coromandel": (-36.8262, 175.7907),
    "mt cook": (-43.7362, 170.0964),
    "dunedin": (-45.8788, 170.5028),
    "nelson": (-41.2706, 173.2840),
    "hamilton": (-37.7870, 175.2793),
    "tauranga": (-37.6878, 176.1651),
    "invercargill": (-46.4132, 168.3538),
    "lake tekapo": (-44.0025, 170.4774)
}

def get_dynamodb_table_name():
    """Loads and returns the DynamoDB table name from the .env file."""
    table_name = os.getenv("DYNAMODB_ACCOMMODATION_TABLE", "thl_accommodation_options")
    return table_name

def get_dynamodb_resource(session=None):
    """Returns a DynamoDB resource using the provided session or creates a new one."""
    return session.resource('dynamodb') if session else boto3.resource('dynamodb')

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two points using the Haversine formula.
    
    Args:
        lat1, lon1: Coordinates of first point in decimal degrees
        lat2, lon2: Coordinates of second point in decimal degrees
        
    Returns:
        float: Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of Earth in kilometers
    
    return c * r

def get_location_coordinates(location):
    """
    Get coordinates for a location name.
    
    Args:
        location: Location name to search for
        
    Returns:
        tuple: (latitude, longitude) or None if not found
    """
    # Convert to lowercase for case-insensitive matching
    location_lower = location.lower()
    
    # Check for exact match
    if location_lower in LOCATION_COORDINATES:
        return LOCATION_COORDINATES[location_lower]
    
    # Check for partial match
    for loc, coords in LOCATION_COORDINATES.items():
        if loc in location_lower or location_lower in loc:
            return coords
    
    return None

def find_accommodation(location: str, family_friendly: bool = None, powered_site: bool = None, 
                      pet_friendly: bool = None, max_distance: float = 50, retry: bool = False, session=None):
    """
    Find available accommodation options near a location with retry capability.
    
    Args:
        location: Location to search near
        family_friendly: Whether accommodation should be family-friendly
        powered_site: Whether powered sites are required
        pet_friendly: Whether accommodation should be pet-friendly
        max_distance: Maximum distance in kilometers to search
        retry: Whether this is a retry attempt
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with accommodation options
    """
    try:
        logger.info(f"Finding accommodation near {location}, retry: {retry}")
        
        # Initialize DynamoDB client with the provided session or default
        dynamodb = get_dynamodb_resource(session)
        
        # Get table name from environment
        table_name = get_dynamodb_table_name()
        accommodation_table = dynamodb.Table(table_name)
        
        try:
            # First try to find accommodations with exact location match
            filter_expression = Attr('accomodation_location').contains(location)
            
            # Add additional filters if specified
            if family_friendly is not None:
                filter_expression = filter_expression & Attr('family_friendly').eq(family_friendly)
            
            if pet_friendly is not None:
                filter_expression = filter_expression & Attr('pet_friendly').eq(pet_friendly)
            
            if powered_site is not None and powered_site:
                filter_expression = filter_expression & Attr('powered_sites_available').gt(0)
            
            response = accommodation_table.scan(
                FilterExpression=filter_expression
            )
            
            accommodations = response['Items']
            
            # If no exact location match or we want to find nearby options
            if not accommodations:
                # Get coordinates for the search location
                search_coords = get_location_coordinates(location)
                
                if not search_coords:
                    return {
                        "status": "error",
                        "response": f"Could not find coordinates for location: {location}"
                    }
                
                # Get all accommodations
                all_response = accommodation_table.scan()
                all_accommodations = all_response['Items']
                
                nearby_accommodations = []
                
                for accommodation in all_accommodations:
                    # Skip if it doesn't meet the filter criteria
                    if family_friendly is not None and accommodation.get('family_friendly') != family_friendly:
                        continue
                    
                    if pet_friendly is not None and accommodation.get('pet_friendly') != pet_friendly:
                        continue
                    
                    if powered_site is not None and powered_site and accommodation.get('powered_sites_available', 0) <= 0:
                        continue
                    
                    # Calculate distance if accommodation has coordinates
                    if 'latitude' in accommodation and 'longitude' in accommodation:
                        try:
                            # Convert string coordinates to float if needed
                            lat = float(accommodation['latitude'].strip('"')) if isinstance(accommodation['latitude'], str) else float(accommodation['latitude'])
                            lon = float(accommodation['longitude'].strip('"')) if isinstance(accommodation['longitude'], str) else float(accommodation['longitude'])
                            
                            distance = calculate_distance(search_coords[0], search_coords[1], lat, lon)
                            
                            # Add distance to accommodation data
                            accommodation['distance_km'] = round(distance, 1)
                            
                            # Include if within max_distance
                            if distance <= max_distance:
                                nearby_accommodations.append(accommodation)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not calculate distance for accommodation {accommodation.get('id')}: {str(e)}")
                
                # Sort by distance
                nearby_accommodations.sort(key=lambda x: x.get('distance_km', float('inf')))
                accommodations = nearby_accommodations
            
            if accommodations:
                # Format the response for better readability
                formatted_accommodations = []
                for acc in accommodations:
                    formatted_acc = {
                        "id": acc.get("id"),
                        "name": acc.get("accomodation_name"),
                        "location": acc.get("accomodation_location"),
                        "type": acc.get("type"),
                        "price_range": acc.get("price_range"),
                        "family_friendly": acc.get("family_friendly"),
                        "pet_friendly": acc.get("pet_friendly"),
                        "amenities": acc.get("amenities")
                    }
                    
                    # Add availability information
                    if "powered_sites_available" in acc:
                        formatted_acc["powered_sites_available"] = acc["powered_sites_available"]
                    if "unpowered_sites_available" in acc:
                        formatted_acc["unpowered_sites_available"] = acc["unpowered_sites_available"]
                    if "cabins_available" in acc:
                        formatted_acc["cabins_available"] = acc["cabins_available"]
                    
                    # Add distance if calculated
                    if "distance_km" in acc:
                        formatted_acc["distance_km"] = acc["distance_km"]
                    
                    formatted_accommodations.append(formatted_acc)
                
                return {
                    "status": "success",
                    "response": formatted_accommodations
                }
            else:
                return {
                    "status": "error",
                    "response": f"No accommodation options found matching your criteria near {location}"
                }
                
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            logger.error(f"DynamoDB ClientError: {error_code} - {error_message}")
            
            # Handle expired token by creating a new session and retrying once
            if error_code == 'ExpiredTokenException' and not retry:
                logger.info("Retrying with refreshed session due to ExpiredTokenException")
                new_session = boto3.Session()
                return find_accommodation(location, family_friendly, powered_site, pet_friendly, 
                                         max_distance, retry=True, session=new_session)
                
            return systemError
    
    except (ProfileNotFound, NoCredentialsError) as e:
        logger.error(f"AWS credential error: {str(e)}")
        return systemError

    except ConnectionError as e:
        logger.error(f"Network error: {str(e)}")
        return systemError

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return systemError

def main(location: str, family_friendly: bool = None, powered_site: bool = None, 
         pet_friendly: bool = None, max_distance: float = 50, session=None):
    """
    Find available accommodation options near a location.
    
    Args:
        location: Location to search near
        family_friendly: Whether accommodation should be family-friendly
        powered_site: Whether powered sites are required
        pet_friendly: Whether accommodation should be pet-friendly
        max_distance: Maximum distance in kilometers to search
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with accommodation options
    """
    logger.info(f"In main accommodation finder called for location: {location}")
    result = find_accommodation(location, family_friendly, powered_site, pet_friendly, max_distance, session=session)
    
    # Convert any Decimal objects to float before returning
    return json.loads(json.dumps(result, cls=DecimalEncoder))

# For direct testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python accommodation_finder.py <location> [options]")
        print("Options:")
        print("  --family-friendly     Only show family-friendly accommodations")
        print("  --powered-site        Only show accommodations with powered sites")
        print("  --pet-friendly        Only show pet-friendly accommodations")
        print("  --max-distance <km>   Maximum distance in kilometers (default: 50)")
        sys.exit(1)
    
    location_arg = sys.argv[1]
    
    # Parse optional arguments
    family_friendly_arg = None
    powered_site_arg = None
    pet_friendly_arg = None
    max_distance_arg = 50
    
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--family-friendly":
            family_friendly_arg = True
            i += 1
        elif sys.argv[i] == "--powered-site":
            powered_site_arg = True
            i += 1
        elif sys.argv[i] == "--pet-friendly":
            pet_friendly_arg = True
            i += 1
        elif sys.argv[i] == "--max-distance" and i + 1 < len(sys.argv):
            try:
                max_distance_arg = float(sys.argv[i + 1])
            except ValueError:
                print(f"Error: max-distance must be a number, got {sys.argv[i + 1]}")
                sys.exit(1)
            i += 2
        else:
            i += 1
    
    result = main(location_arg, family_friendly_arg, powered_site_arg, pet_friendly_arg, max_distance_arg)
    print(json.dumps(result, indent=2, cls=DecimalEncoder))
    sys.exit(0 if result and result.get("status") == "success" else 1)
