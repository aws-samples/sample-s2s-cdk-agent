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
name: applianceTroubleshooting
description: Provides troubleshooting steps for common campervan appliance issues
parameters:
  - name: appliance_type
    type: string
    description: Type of appliance (fridge, stove, heater, water_pump, power_system)
    required: true
  - name: issue_description
    type: string
    description: Description of the issue
    required: true
  - name: vehicle_model
    type: string
    description: Model of the campervan
    required: false
"""

import boto3
import logging
import json
import os
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
    "response": "Sorry, we couldn't find troubleshooting steps for the issue you described."
}

systemError = {
    "status": "error",
    "response": "We are currently unable to provide troubleshooting assistance. Please try again later."
}

# Troubleshooting guides for common issues
TROUBLESHOOTING_GUIDES = {
    "fridge": {
        "not_cooling": [
            "Check that the fridge is turned on and set to the correct mode (gas, 12V, or 240V).",
            "Ensure the campervan is parked on a level surface.",
            "Check that the gas bottle is turned on and has gas (if using gas mode).",
            "Verify that the 12V connection is working (if using 12V mode).",
            "Check that the campervan is connected to mains power (if using 240V mode).",
            "Allow 24 hours for the fridge to reach optimal temperature after turning on.",
            "Avoid overfilling the fridge as this can restrict air circulation."
        ],
        "making_noise": [
            "Some noise is normal during operation, especially when the cooling cycle starts.",
            "Check that the fridge is level - uneven positioning can cause increased noise.",
            "Ensure nothing is touching the cooling unit at the back of the fridge.",
            "Check that the fridge is not set to maximum cooling unnecessarily."
        ],
        "freezing_food": [
            "Adjust the temperature control to a lower setting.",
            "Ensure food is not placed against the cooling plate at the back of the fridge.",
            "Check that the door seals properly and is not being left open."
        ]
    },
    "stove": {
        "won't_light": [
            "Ensure the gas bottle is turned on and has gas.",
            "Check that the gas isolation valve for the stove is open.",
            "For piezo ignition: Press and hold the knob while clicking the ignition several times.",
            "For manual lighting: Use a lighter or match while pressing and holding the knob.",
            "Hold the knob in for 10-15 seconds after lighting to allow the thermocouple to heat up.",
            "Check for blockages in the burner and clean if necessary."
        ],
        "weak_flame": [
            "Check that the gas bottle is not running low.",
            "Ensure the burner is clean and free from food debris.",
            "Check that the correct jet is installed for the type of gas being used.",
            "Verify that the gas regulator is functioning correctly."
        ],
        "gas_smell": [
            "Turn off the gas bottle immediately.",
            "Open all windows and doors to ventilate the campervan.",
            "Do not use any electrical switches or naked flames.",
            "Check that all knobs are in the off position.",
            "Contact THL support for assistance - do not use the stove until it has been checked."
        ]
    },
    "heater": {
        "not_turning_on": [
            "Check that the campervan has sufficient battery power.",
            "Ensure the gas bottle is turned on and has gas (for gas heaters).",
            "Verify that the heater isolation switch is turned on.",
            "Check the control panel settings and increase the temperature setting.",
            "Reset the heater by turning it off at the control panel, waiting 10 seconds, then turning it back on."
        ],
        "blowing_cold_air": [
            "Allow the heater a few minutes to warm up after starting.",
            "Check that the gas bottle is not empty (for gas heaters).",
            "Ensure the air intake and outlets are not blocked.",
            "Check that the correct temperature is set on the control panel."
        ],
        "making_unusual_noise": [
            "Some noise is normal during startup and shutdown cycles.",
            "Check that the air intake is not blocked or restricted.",
            "Ensure the campervan is parked on a level surface.",
            "If a high-pitched whine persists, the fan may need servicing - contact THL support."
        ]
    },
    "water_pump": {
        "not_working": [
            "Check that the water tank has sufficient water.",
            "Ensure the pump switch is turned on.",
            "Verify that the campervan has sufficient battery power.",
            "Check for any tripped circuit breakers or blown fuses.",
            "Listen for the pump running when a tap is opened - if you hear it running but no water flows, there may be an airlock."
        ],
        "running_continuously": [
            "Check for any open taps or leaks in the water system.",
            "Ensure the water tank is not empty.",
            "Check for air in the system - this can be removed by running each tap until water flows smoothly.",
            "The pressure switch may need adjustment - contact THL support if the issue persists."
        ],
        "pulsing_or_cycling": [
            "This is often caused by a small leak or dripping tap.",
            "Check all taps are fully closed.",
            "Inspect visible water lines for leaks.",
            "The water pump accumulator tank may need recharging - contact THL support if the issue persists."
        ]
    },
    "power_system": {
        "no_12v_power": [
            "Check the main battery isolation switch is turned on.",
            "Verify that the leisure battery has sufficient charge.",
            "Check for any tripped circuit breakers or blown fuses in the 12V system.",
            "If connected to mains power, ensure the battery charger is working.",
            "Check that the battery terminals are clean and securely connected."
        ],
        "no_240v_power": [
            "Verify that the campervan is properly connected to a mains power supply.",
            "Check that the site's power outlet is working.",
            "Inspect the RCD (residual current device) and reset if tripped.",
            "Check for any tripped circuit breakers in the campervan's consumer unit.",
            "Ensure the mains connection cable is not damaged."
        ],
        "battery_not_charging": [
            "When driving: Check the alternator fuse and connections.",
            "When on mains power: Verify that the battery charger is working.",
            "With solar panels: Ensure panels are clean and positioned for maximum sunlight.",
            "Check that the battery terminals are clean and securely connected.",
            "The battery may be at the end of its life if it's more than 3-5 years old."
        ]
    }
}

def troubleshoot_appliance(appliance_type: str, issue_description: str, vehicle_model: str = None, 
                          retry: bool = False, session=None):
    """
    Provide troubleshooting steps for campervan appliance issues with retry capability.
    
    Args:
        appliance_type: Type of appliance (fridge, stove, heater, water_pump, power_system)
        issue_description: Description of the issue
        vehicle_model: Model of the campervan
        retry: Whether this is a retry attempt
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with troubleshooting steps
    """
    try:
        logger.info(f"Troubleshooting {appliance_type} issue: {issue_description}, retry: {retry}")
        
        appliance_type = appliance_type.lower()
        
        if appliance_type not in TROUBLESHOOTING_GUIDES:
            return {
                "status": "error",
                "response": f"Invalid appliance type: {appliance_type}. Must be one of: fridge, stove, heater, water_pump, power_system"
            }
        
        # Find the most relevant issue based on the description
        issue_description = issue_description.lower()
        relevant_issue = None
        
        for issue, steps in TROUBLESHOOTING_GUIDES[appliance_type].items():
            if issue in issue_description:
                relevant_issue = issue
                break
        
        # If no exact match, use the first issue as default
        if not relevant_issue:
            relevant_issue = list(TROUBLESHOOTING_GUIDES[appliance_type].keys())[0]
        
        troubleshooting_steps = TROUBLESHOOTING_GUIDES[appliance_type][relevant_issue]
        
        # Add vehicle model specific information if available
        model_specific_info = None
        if vehicle_model:
            # In a real implementation, this would look up model-specific information
            # For this demo, we'll just acknowledge the model
            model_specific_info = f"These steps are general guidelines for all THL campervans. Your {vehicle_model} may have specific features - please refer to the vehicle manual for detailed instructions."
        
        return {
            "status": "success",
            "response": {
                "appliance": appliance_type,
                "issue": relevant_issue,
                "troubleshooting_steps": troubleshooting_steps,
                "model_specific_info": model_specific_info
            }
        }
    
    except (ProfileNotFound, NoCredentialsError) as e:
        logger.error(f"AWS credential error: {str(e)}")
        return systemError

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(f"AWS ClientError: {error_code} - {error_message}")
        
        # Handle expired token by creating a new session and retrying once
        if error_code == 'ExpiredTokenException' and not retry:
            logger.info("Retrying with refreshed session due to ExpiredTokenException")
            new_session = boto3.Session()
            return troubleshoot_appliance(appliance_type, issue_description, vehicle_model, 
                                         retry=True, session=new_session)
            
        return systemError

    except ConnectionError as e:
        logger.error(f"Network error: {str(e)}")
        return systemError

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return systemError

def main(appliance_type: str, issue_description: str, vehicle_model: str = None, session=None):
    """
    Provide troubleshooting steps for campervan appliance issues.
    
    Args:
        appliance_type: Type of appliance (fridge, stove, heater, water_pump, power_system)
        issue_description: Description of the issue
        vehicle_model: Model of the campervan
        session: Optional boto3 session to use
        
    Returns:
        dict: Result with troubleshooting steps
    """
    logger.info(f"In main appliance troubleshooting called for {appliance_type}: {issue_description}")
    return troubleshoot_appliance(appliance_type, issue_description, vehicle_model, session=session)

# For direct testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python appliance_troubleshooting.py <appliance_type> <issue_description> [vehicle_model]")
        print("appliance_type can be: fridge, stove, heater, water_pump, power_system")
        sys.exit(1)
    
    appliance_type_arg = sys.argv[1]
    issue_description_arg = sys.argv[2]
    vehicle_model_arg = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = main(appliance_type_arg, issue_description_arg, vehicle_model_arg)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result and result.get("status") == "success" else 1)
