from typing import Annotated, Union
from pydantic import Field
from mcp_server import mcp_server
import logging
import knowledge_base_lookup
import retrieve_user_profile

logger = logging.getLogger(__name__)

# Knowledge Base Lookup Tool
@mcp_server.tool(
    name="lookup",
    description="Runs query against a knowledge base to retrieve information."
)
async def lookup_tool(
    query: Annotated[str, Field(description="the query to search")]
) -> dict:
    """Look up information in the knowledge base"""
    try:
        logger.info(f"Knowledge base lookup query: {query}")
        results = knowledge_base_lookup.main(query)
        return results  
    except Exception as e:
        logger.error(f"Error in knowledge base lookup: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}

# User Profile Search Tool
@mcp_server.tool(
    name="userProfileSearch",
    description="Search for a user's account and phone plan information by phone number"
)
async def user_profile_search_tool(
    phone_number: Annotated[Union[int, str], Field(description="the user's phone number")]
) -> dict:
    """Search for user profile and account information"""
    try:
        phone_str = str(phone_number)
        logger.info(f"User profile search for: {phone_str}")
        results = retrieve_user_profile.main(phone_str)
        return results  
    except Exception as e:
        logger.error(f"Error in user profile search: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}
