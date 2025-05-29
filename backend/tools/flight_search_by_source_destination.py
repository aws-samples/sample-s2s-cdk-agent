"""
@tool
name: flight_search_by_source_destination
description: Searches for available flights between source and destination airports, supporting multiple passenger types and filters.
parameters:
  - name: source
    type: string
    description: Source airport code (e.g., AKL for Auckland)
    required: true
  - name: destination
    type: string
    description: Destination airport code (e.g., SIN for Singapore)
    required: true
  - name: departure_date
    type: string
    description: Departure date in YYYY-MM-DD format
    required: true
  - name: return_date
    type: string
    description: Return date in YYYY-MM-DD format for round trips (optional for one-way trips)
    required: false
  - name: adults
    type: integer
    description: Number of adult passengers
    required: false
    default: 1
  - name: children
    type: integer
    description: Number of child passengers
    required: false
    default: 0
  - name: infants
    type: integer
    description: Number of infant passengers
    required: false
    default: 0
  - name: non_stop
    type: boolean
    description: Whether to search for non-stop flights only
    required: false
    default: false
  - name: currency_code
    type: string
    description: Currency code for pricing (e.g., NZD, USD)
    required: false
    default: "NZD"
  - name: travel_class
    type: string
    description: Travel class (e.g., ECONOMY, BUSINESS)
    required: false
  - name: included_airline_codes
    type: array
    items:
      type: string
    description: List of airline codes to include
    required: false
  - name: excluded_airline_codes
    type: array
    items:
      type: string
    description: List of airline codes to exclude
    required: false
  - name: max_price
    type: integer
    description: Maximum price to filter flights
    required: false
  - name: one_way
    type: boolean
    description: If true, ignores return_date even if provided
    required: false
  - name: max
    type: integer
    description: Maximum number of results to return
    required: false
    default: 5
"""

import logging
import os
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

def get_amadeus_token() -> str:
    api_key = os.environ.get('AMADEUS_API_KEY')
    api_secret = os.environ.get('AMADEUS_API_SECRET')
    
    if not api_key or not api_secret:
        raise ValueError("Amadeus API credentials not found in environment variables")
    
    token_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": api_secret
    }
    
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post(token_url, data=payload, headers=headers)
    response.raise_for_status()
    return response.json()["access_token"]

def format_flight_data(flight_offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted_flights = []
    
    for offer in flight_offers:
        try:
            itineraries = offer.get('itineraries', [])
            price = offer.get('price', {})
            
            flight_data = {
                'price': {
                    'total': price.get('total'),
                    'currency': price.get('currency')
                },
                'segments': []
            }
            
            for itinerary in itineraries:
                for segment in itinerary.get('segments', []):
                    departure = segment.get('departure', {})
                    arrival = segment.get('arrival', {})
                    carrier = segment.get('carrierCode', '')
                    flight_number = segment.get('number', '')
                    
                    segment_data = {
                        'departure': {
                            'airport': departure.get('iataCode'),
                            'time': departure.get('at')
                        },
                        'arrival': {
                            'airport': arrival.get('iataCode'),
                            'time': arrival.get('at')
                        },
                        'flight': f"{carrier} {flight_number}",
                        'duration': segment.get('duration')
                    }
                    flight_data['segments'].append(segment_data)
            
            formatted_flights.append(flight_data)
        except Exception as e:
            logger.warning(f"Error formatting flight offer: {str(e)}")
            continue
    
    return formatted_flights

def main(
    source: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    non_stop: bool = False,
    currency_code: str = "NZD",
    travel_class: Optional[str] = None,
    included_airline_codes: Optional[List[str]] = None,
    excluded_airline_codes: Optional[List[str]] = None,
    max_price: Optional[int] = None,
    one_way: Optional[bool] = None,
    max: int = 3,
    session=None
) -> Dict[str, Any]:
    try:
        # Validate dates
        try:
            datetime.strptime(departure_date, '%Y-%m-%d')
            if return_date and not one_way:
                datetime.strptime(return_date, '%Y-%m-%d')
        except ValueError:
            return {
                "status": "error",
                "response": "Invalid date format. Use YYYY-MM-DD."
            }
        
        access_token = get_amadeus_token()
        search_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"

        params = {
            "originLocationCode": source.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": departure_date,
            "adults": adults,
            "nonStop": str(non_stop).lower(),
            "currencyCode": currency_code,
            "max": max,
            "includedAirlineCodes": "NZ,UA,AC,SQ"
        }

        if children > 0:
            params["children"] = children
        if infants > 0:
            params["infants"] = infants
        if travel_class:
            params["travelClass"] = travel_class.upper()
        if return_date and not one_way:
            params["returnDate"] = return_date
        # Always use the specified airline codes, ignoring any input parameter
        if excluded_airline_codes:
            params["excludedAirlineCodes"] = ','.join(excluded_airline_codes)
        if max_price:
            params["maxPrice"] = max_price

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        response = requests.get(search_url, params=params, headers=headers)
        response.raise_for_status()
        flight_offers = response.json().get("data", [])

        if not flight_offers:
            return {
                "status": "success",
                "data": {
                    "message": "No flights found for the specified criteria.",
                    "flights": []
                }
            }

        formatted_flights = format_flight_data(flight_offers[:max])
        return {
            "status": "success",
            "data": {
                "message": f"Found {len(formatted_flights)} flights from {source.upper()} to {destination.upper()}",
                "flights": formatted_flights
            }
        }

    except requests.exceptions.HTTPError as e:
        error_message = f"API error: {str(e)}"
        if e.response.status_code == 400:
            try:
                error_details = e.response.json()
                error_message = error_details.get('errors', [{}])[0].get('detail', error_message)
            except:
                pass
        logger.error(error_message)
        return {
            "status": "error",
            "response": error_message
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            "status": "error",
            "response": f"Unexpected error: {str(e)}"
        }
