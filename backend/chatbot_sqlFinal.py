import os, sys
import logging
from typing import Dict, Any, List, Set, Tuple
import pandas as pd
import re
import numpy as np
from fuzzywuzzy import fuzz
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the absolute path of the current file
current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)
app_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(app_dir)

# Add the project root to sys.path
sys.path.append(project_root)

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable is not set")
    raise ValueError("GEMINI_API_KEY environment variable is not set")

# Cache for dataframe to avoid repeated database calls
_df_cache = None
_data_analysis_cache = None
_conversation_context = {}  # Store conversation context by session ID
_entity_extraction_llm = None
_search_llm = None

# Sample data for testing - replace this with your actual data loading function
from connection import get_quotation_data_as_df
def get_quotation_data():
    """Get quotation data with caching to avoid repeated database calls"""
    global _df_cache
    if _df_cache is None:
        try:
            # Use the function from connection.py to get data from the database
            _df_cache = get_quotation_data_as_df()
            
            # Check if we got valid data
            if _df_cache is None or _df_cache.empty:
                logger.error("Failed to retrieve data from database or empty dataset returned")
                raise ValueError("Failed to retrieve data from database or empty dataset returned")
            
            logger.info(f"Loaded quotation data from database with {len(_df_cache)} rows")
            
            # Ensure the dataframe has the required columns
            required_columns = ['invoice_no', 'company_name', 'item_description', 
                               'category', 'quantity', 'unit_price', 'subtotal', 'tax', 'total']
            
            missing_columns = [col for col in required_columns if col not in _df_cache.columns]
            if missing_columns:
                logger.error(f"Database data is missing required columns: {missing_columns}")
                raise ValueError(f"Database data is missing required columns: {missing_columns}")
                
        except Exception as e:
            logger.error(f"Error loading quotation data from database: {e}")
            raise ValueError(f"Failed to load quotation data from database: {e}")
    
    return _df_cache

def get_entity_extraction_llm():
    """Get or initialize the LLM for entity extraction"""
    global _entity_extraction_llm
    if _entity_extraction_llm is None:
        try:
            _entity_extraction_llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash", 
                api_key=GEMINI_API_KEY,
                temperature=0.1  # Low temperature for more consistent entity extraction
            )
            logger.info("Initialized entity extraction LLM")
        except Exception as e:
            logger.error(f"Error initializing entity extraction LLM: {e}")
            raise ValueError("Failed to initialize entity extraction LLM")
    return _entity_extraction_llm

def get_search_llm():
    """Get or initialize the LLM for search matching"""
    global _search_llm
    if _search_llm is None:
        try:
            _search_llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",  # Using the supported model name
                api_key=GEMINI_API_KEY,
                temperature=0.2
            )
            logger.info("Initialized search matching LLM")
        except Exception as e:
            logger.error(f"Error initializing search matching LLM: {e}")
            raise ValueError("Failed to initialize search matching LLM")
    return _search_llm

def analyze_data():
    """Analyze the data to extract useful information for quotations"""
    global _data_analysis_cache
    if _data_analysis_cache is None:
        try:
            df = get_quotation_data()
            
            # Get categories
            categories = df['category'].unique().tolist()
            
            # Extract all unique service descriptions for matching
            all_services = {}
            for _, row in df.iterrows():
                service_id = f"{row['invoice_no']}_{row['item_description']}"
                all_services[service_id] = {
                    'category': row['category'],
                    'description': row['item_description'],
                    'unit_price': row['unit_price'],
                    'subtotal': row['subtotal'],
                    'tax': row['tax'],
                    'total': row['total']
                }
            
            # Analyze each category
            category_analysis = {}
            for category in categories:
                category_df = df[df['category'] == category]
                
                # Get common services
                common_services = []
                for _, row in category_df.drop_duplicates(subset=['item_description']).iterrows():
                    common_services.append({
                        'description': row['item_description'],
                        'unit_price': row['unit_price']
                    })
                
                # Get price ranges
                price_range = {
                    'min': category_df['unit_price'].min(),
                    'max': category_df['unit_price'].max(),
                    'median': category_df['unit_price'].median(),
                    'mean': category_df['unit_price'].mean()
                }
                
                # Store the analysis
                category_analysis[category] = {
                    'count': len(category_df),
                    'common_services': common_services,
                    'price_range': price_range,
                    'services': category_df['item_description'].tolist()
                }
            
            # Store the analysis in the cache
            _data_analysis_cache = {
                'categories': categories,
                'category_analysis': category_analysis,
                'all_services': all_services
            }
            
            logger.info("Data analysis completed")
        except Exception as e:
            logger.error(f"Error analyzing data: {e}")
            raise ValueError("Failed to analyze data")
    
    return _data_analysis_cache

def classify_user_intent(message, context=None):
    """
    Classify user intent into categories: information_request, quotation_request, confirmation, etc.
    """
    message_lower = message.lower()
    
    # Check for informational queries
    info_keywords = ["what is", "how much", "price", "cost", "average", "popular", "common", "statistics", "tell me about", "info"]
    if any(keyword in message_lower for keyword in info_keywords):
        # Further classify the type of information
        if any(term in message_lower for term in ["most popular", "common", "frequently"]):
            return "popular_services_info"
        elif any(term in message_lower for term in ["price", "cost", "how much", "average cost"]):
            return "price_info"
        return "information_request"
    
    # Check for quotation requests
    quote_keywords = ["quote", "quotation", "get a quote", "want to", "need to", "service", "hire", "book"]
    if any(keyword in message_lower for keyword in quote_keywords):
        return "quotation_request"
    
    # Check for confirmation or rejection
    if is_confirmation_message(message):
        return "confirmation"
    if is_negative_response(message):
        return "rejection"
    
    # Check if this is a direct answer to a question
    if context and context.get('last_question_type'):
        return "direct_answer"
    
    # Default to generic request
    return "generic_request"

def get_price_estimate(category, service_type=None):
    """Get price estimate information for a category and optional service type"""
    analysis = analyze_data()
    
    if category in analysis['category_analysis']:
        category_data = analysis['category_analysis'][category]
        price_range = category_data.get('price_range', {})
        
        # Basic price range information
        price_info = f"For {category}, prices typically range from RM {price_range.get('min', 0):.2f} to RM {price_range.get('max', 0):.2f}."
        
        # If service type is specified, try to provide more specific information
        if service_type:
            df = get_quotation_data()
            category_df = df[df['category'] == category]
            
            # Create a filter based on service type keywords
            if service_type == 'chemical_cleaning':
                filter_terms = ['chemical', 'chem']
            elif service_type == 'basic_servicing':
                filter_terms = ['basic', 'general', 'normal']
            elif service_type == 'gas_topup':
                filter_terms = ['gas', 'top up', 'refill']
            else:
                filter_terms = [service_type.replace('_', ' ')]
                
            # Apply the filter
            filtered_df = category_df[category_df['item_description'].str.lower().apply(
                lambda x: any(term in x.lower() for term in filter_terms))]
            
            # If we have results after filtering, provide more specific price info
            if not filtered_df.empty:
                service_type_display = service_type.replace('_', ' ').title()
                specific_min = filtered_df['unit_price'].min()
                specific_max = filtered_df['unit_price'].max()
                specific_median = filtered_df['unit_price'].median()
                
                price_info = f"For {category} - {service_type_display}, prices typically range from RM {specific_min:.2f} to RM {specific_max:.2f}, with the median price being RM {specific_median:.2f}."
        
        # Add factors that affect pricing
        if category == 'Aircon Servicing':
            price_info += "\n\nFactors that affect pricing include:\n- Type of aircon unit (wall, ceiling, cassette)\n- Horsepower of the unit\n- Type of service (basic servicing vs chemical cleaning)\n- Number of units"
        elif category == 'Aircon Installation':
            price_info += "\n\nFactors that affect pricing include:\n- Type of aircon unit\n- Horsepower/BTU rating\n- Brand\n- Installation complexity\n- Additional piping or materials needed"
        elif category == 'Aircon Repair':
            price_info += "\n\nFactors that affect pricing include:\n- Type of issue (gas leak, electrical problem, component replacement)\n- Type and brand of aircon unit\n- Severity of the problem\n- Parts required"
        elif category == 'Plumber':
            price_info += "\n\nFactors that affect pricing include:\n- Type of plumbing fixture (toilet, sink, pipe)\n- Nature of the issue (leaking, clogged, installation)\n- Complexity of the repair\n- Materials required"
        
        return price_info
    
    return f"I don't have detailed pricing information for {category} at the moment. Would you like me to provide a specific quote based on your requirements?"

def get_popular_services(category, service_type=None):
    """Get popular services for a category and optional service type based on analyzed data"""
    analysis = analyze_data()
    df = get_quotation_data()
    
    if category in analysis['category_analysis']:
        # Filter by category
        category_df = df[df['category'] == category]
        
        # If service type is specified, further filter the data
        if service_type:
            # Create a filter based on service type keywords
            if service_type == 'chemical_cleaning':
                filter_terms = ['chemical', 'chem']
            elif service_type == 'basic_servicing':
                filter_terms = ['basic', 'general', 'normal']
            elif service_type == 'gas_topup':
                filter_terms = ['gas', 'top up', 'refill']
            else:
                filter_terms = [service_type.replace('_', ' ')]
                
            # Apply the filter
            filtered_df = category_df[category_df['item_description'].str.lower().apply(
                lambda x: any(term in x.lower() for term in filter_terms))]
            
            # If we have results after filtering, use them; otherwise, fall back to category
            if not filtered_df.empty:
                # Get service counts
                service_counts = filtered_df['item_description'].value_counts()
                
                # Get the most common services with counts
                common_services = []
                for desc, count in service_counts.head(5).items():
                    price = filtered_df[filtered_df['item_description'] == desc]['unit_price'].iloc[0]
                    common_services.append({
                        'description': desc,
                        'unit_price': price,
                        'count': count
                    })
                
                if common_services:
                    service_type_display = service_type.replace('_', ' ').title()
                    services_text = "\n".join([f"- {s['description']} (RM {s['unit_price']:.2f})" for s in common_services])
                    return f"Our most popular {category} - {service_type_display} services are:\n\n{services_text}"
        
        # If no service type specified or no matches found, return category-level popular services
        service_counts = category_df['item_description'].value_counts()
        common_services = []
        
        for desc, count in service_counts.head(5).items():
            price = category_df[category_df['item_description'] == desc]['unit_price'].iloc[0]
            common_services.append({
                'description': desc,
                'unit_price': price,
                'count': count  
            })
            
        if common_services:
            services_text = "\n".join([f"- {s['description']} (RM {s['unit_price']:.2f})" for s in common_services])
            return f"Our most popular {category} services are:\n\n{services_text}"
    
    return f"I don't have detailed popularity information for {category} services at the moment. Would you like me to provide a quote instead?"

def handle_information_request(message, context):
    """Handle information requests about services, pricing, popularity, etc."""
    try:
        # Determine what kind of information is being requested
        intent = classify_user_intent(message)
        
        # Extract entities to determine the category
        entities = extract_entities_with_llm(message, context)
        category = entities.get('category') or context.get('category')
        service_type = entities.get('service_type') or context.get('service_type')
        
        # Update the context with any new information
        if category and (not context.get('category') or context.get('category') != category):
            context['category'] = category
            logger.info(f"Updated context category = {category}")
        
        if service_type and (not context.get('service_type') or context.get('service_type') != service_type):
            context['service_type'] = service_type
            logger.info(f"Updated context service_type = {service_type}")
        
        # Handle price information requests
        if intent == "price_info" and category:
            price_info = get_price_estimate(category, service_type)
            popular_services = get_popular_services(category, service_type)
            response = f"Here's the information about pricing:\n\n{price_info}\n\n"
            if popular_services:
                response += f"{popular_services}\n\n"
            response += "Would you like me to provide a specific quotation based on your requirements?"
            return {"response": response, "has_quotation": False, "needs_more_info": False}
        
        # Handle requests for popular services
        elif intent == "popular_services_info" and category:
            popular_services = get_popular_services(category, service_type)
            if popular_services:
                return {"response": popular_services, "has_quotation": False, "needs_more_info": False}
            else:
                # Fall back to a generic response if we can't provide specific information
                analysis = analyze_data()
                if category in analysis['category_analysis']:
                    common_services = analysis['category_analysis'][category]['common_services'][:5]
                    
                    if common_services:
                        services_text = "\n".join([f"- {s['description']} (RM {s['unit_price']:.2f})" for s in common_services])
                        response = f"Based on our data, here are some common {category} services:\n\n{services_text}\n\nWould you like a quote for any of these services?"
                        return {"response": response, "has_quotation": False, "needs_more_info": False}
                
                # If we still don't have information, ask for more details
                return {
                    "response": f"I'd be happy to tell you about popular {category} services. Could you specify what type of {category.lower()} you're interested in?",
                    "has_quotation": False,
                    "needs_more_info": True
                }
        
        # If we couldn't extract a category but the intent is informational
        elif intent in ["price_info", "popular_services_info"] and not category:
            return {
                "response": "I can provide information about services and pricing for aircon servicing, aircon installation, aircon repair, and plumbing. Which category are you interested in?",
                "has_quotation": False,
                "needs_more_info": True
            }
        
        # Default response for information requests
        return {
            "response": "I can provide information about our services, pricing, and popular options. Could you please specify which service category you're interested in (aircon servicing, aircon installation, aircon repair, or plumbing)?",
            "has_quotation": False,
            "needs_more_info": True
        }
    
    except Exception as e:
        logger.error(f"Error handling information request: {e}")
        return {
            "response": "I apologize, but I encountered an error while retrieving that information. Could you please try asking in a different way?",
            "has_quotation": False,
            "needs_more_info": True
        }

def extract_entities_with_llm(message: str, context: Dict = None) -> Dict:
    """Extract entities from a message using the LLM"""
    try:
        # Special case for when user just says "aircon" - automatically interpret as Aircon Servicing
        message_lower = message.lower().strip()
        if message_lower == "aircon":
            return {'category': 'Aircon Servicing'}
        
        # Check for direct answers to previous questions first
        if context and context.get('last_question_type'):
            direct_response = handle_direct_response(message, context.get('last_question_type'))
            if direct_response:
                logger.info(f"Extracted direct response: {direct_response}")
                return direct_response
        
        # Get the LLM
        llm = get_entity_extraction_llm()
        
        # Get data analysis to understand available categories and services
        analysis = analyze_data()
        categories = analysis['categories']
        
        # Create a system prompt for entity extraction
        system_prompt = f"""You are an entity extraction assistant for a quotation system. Extract structured information from the user's message about service requests.

Available service categories: {', '.join(categories)}

Extract the following entities if present:
1. category: The service category (e.g., Aircon Servicing, Aircon Installation, Aircon Repair, Plumber)
2. unit_type: For aircon, the type of unit (e.g., wall, ceiling, cassette, window)
3. service_type: The type of service needed (e.g., chemical_cleaning, basic_servicing, gas_topup, repair, installation)
4. hp_size: For aircon, the horsepower (e.g., 1.0, 1.5, 2.0, 2.5, 3.0)
5. brand: For aircon, the brand name (e.g., daikin, panasonic, samsung, lg)
6. fixture_type: For plumbing, the type of fixture (e.g., toilet, sink, pipe, water_heater, water_tank)
7. issue_type: For repairs, the type of issue (e.g., leaking, clogged, broken, not_cooling, noise)
8. quantity: The number of units or services needed

Return ONLY a JSON object with the extracted entities. If an entity is not present, do not include it in the JSON.
"""
        
        # Create the prompt
        prompt = f"Extract service request information from this message: {message}"
        
        # Invoke the LLM
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the JSON from the response
        response_text = response.content
        
        # Try to find and parse JSON in the response
        try:
            # Look for JSON pattern
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                extracted_info = json.loads(json_str)
            else:
                # If no JSON pattern found, try to parse the whole response
                extracted_info = json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, extract information manually
            logger.warning(f"Failed to parse JSON from LLM response: {response_text}")
            extracted_info = {}
            
            # Extract category
            if "category" in response_text.lower():
                for category in categories:
                    if category.lower() in response_text.lower():
                        extracted_info["category"] = category
                        break
            
            # Extract other common fields
            for field in ["unit_type", "service_type", "hp_size", "brand", "fixture_type", "issue_type", "quantity"]:
                if field in response_text.lower():
                    field_match = re.search(rf"{field}[:\s]+([a-zA-Z0-9_\.]+)", response_text, re.IGNORECASE)
                    if field_match:
                        extracted_info[field] = field_match.group(1)
        
        # Manual extraction for common terms
        if "aircon" in message_lower and not "category" in extracted_info:
            # If message contains "aircon" and no category was extracted, default to Aircon Servicing
            extracted_info["category"] = "Aircon Servicing"
            
        if "wall mounted" in message.lower() or "wall-mounted" in message.lower():
            extracted_info["unit_type"] = "wall"
        elif "window" in message.lower():
            extracted_info["unit_type"] = "window"
        elif "cassette" in message.lower():
            extracted_info["unit_type"] = "cassette"
        elif "ceiling" in message.lower():
            extracted_info["unit_type"] = "ceiling"
        elif "split" in message.lower() and "unit" in message.lower():
            extracted_info["unit_type"] = "wall"  # Most split units are wall-mounted
        
        # Manual extraction for horsepower
        hp_match = re.search(r'(\d+(\.\d+)?)\s*hp', message.lower())
        if hp_match:
            extracted_info["hp_size"] = hp_match.group(1)
        elif re.match(r'^\d+(\.\d+)?$', message.strip()):
            # If the message is just a number, it might be the HP size or quantity
            num_value = float(message.strip())
            if context and context.get('last_question_type') == 'hp_size':
                extracted_info["hp_size"] = str(num_value)
            elif context and context.get('last_question_type') == 'quantity':
                extracted_info["quantity"] = int(num_value)
            elif num_value > 0 and num_value <= 5:
                # Likely HP size if between 0 and 5
                extracted_info["hp_size"] = str(num_value)
            elif num_value > 0 and num_value <= 20:
                # Likely quantity if between 1 and 20
                extracted_info["quantity"] = int(num_value)
        
        quantity_match = re.match(r'^\s*(\d+)\s*$', message)
        if quantity_match and not "hp_size" in extracted_info:
            extracted_info["quantity"] = int(quantity_match.group(1))
        
        # Extract service type from common terms
        if "general cleaning" in message.lower() or "basic cleaning" in message.lower():
            extracted_info["service_type"] = "basic_servicing"
        elif "chemical" in message.lower() or "chemical wash" in message.lower():
            extracted_info["service_type"] = "chemical_cleaning"
        elif "gas" in message.lower() or "top up" in message.lower() or "refill" in message.lower():
            extracted_info["service_type"] = "gas_topup"
        
        # Extract fixture type for plumbing
        if "toilet" in message.lower() or "wc" in message.lower():
            extracted_info["fixture_type"] = "toilet"
        elif "sink" in message.lower() or "basin" in message.lower():
            extracted_info["fixture_type"] = "sink"
        elif "pipe" in message.lower() or "drain" in message.lower():
            extracted_info["fixture_type"] = "pipe"
        
        # Extract issue type
        if "leak" in message.lower():
            extracted_info["issue_type"] = "leaking"
        elif "clog" in message.lower() or "block" in message.lower():
            extracted_info["issue_type"] = "clogged"
        
        logger.info(f"Extracted entities: {extracted_info}")
        return extracted_info
    
    except Exception as e:
        logger.error(f"Error extracting entities with LLM: {e}")
        return {}
    
def determine_missing_info_with_llm(info: Dict) -> Dict:
    """Use the LLM to determine what information is missing and generate a question to ask the user"""
    try:
        # If we don't have a category yet, ask for it first
        if not info.get('category'):
            return {
                'has_enough_info': False,
                'missing_key': 'category',
                'next_question': "What type of service are you looking for? (e.g., Aircon Servicing, Aircon Installation, Aircon Repair, or Plumber)"
            }
        
        # Check if we have the basic required information based on category
        category = info.get('category')
        
        # Define required fields by category
        required_fields = {
            'Aircon Servicing': ['unit_type', 'service_type', 'hp_size', 'quantity'],
            'Aircon Installation': ['unit_type', 'hp_size', 'brand', 'quantity'],
            'Aircon Repair': ['unit_type', 'issue_type', 'quantity'],
            'Plumber': ['fixture_type', 'issue_type', 'quantity']
        }
        
        # If we have a category, check for missing required fields
        if category and category in required_fields:
            for field in required_fields[category]:
                if field not in info or not info[field]:
                    # Generate appropriate question based on missing field
                    if field == 'unit_type':
                        return {
                            'has_enough_info': False,
                            'missing_key': 'unit_type',
                            'next_question': "What type of aircon unit is it (e.g., window, split, cassette)?"
                        }
                    elif field == 'service_type':
                        return {
                            'has_enough_info': False,
                            'missing_key': 'service_type',
                            'next_question': "What type of service do you need (e.g., basic servicing, chemical cleaning, gas top-up)?"
                        }
                    elif field == 'hp_size':
                        return {
                            'has_enough_info': False,
                            'missing_key': 'hp_size',
                            'next_question': "What is the horsepower (HP) of the aircon unit?"
                        }
                    elif field == 'quantity':
                        # Customize the quantity question based on the category
                        if category == 'Plumber':
                            fixture_type = info.get('fixture_type', 'plumbing fixtures')
                            return {
                                'has_enough_info': False,
                                'missing_key': 'quantity',
                                'next_question': f"How many {fixture_type}s need service?"
                            }
                        else:
                            return {
                                'has_enough_info': False,
                                'missing_key': 'quantity',
                                'next_question': "How many aircon units do you want to service?"
                            }
                    elif field == 'brand':
                        return {
                            'has_enough_info': False,
                            'missing_key': 'brand',
                            'next_question': "What brand of aircon do you want to install?"
                        }
                    elif field == 'fixture_type':
                        return {
                            'has_enough_info': False,
                            'missing_key': 'fixture_type',
                            'next_question': "What type of plumbing fixture needs service (e.g., toilet, sink, pipe)?"
                        }
                    elif field == 'issue_type':
                        if category == 'Plumber':
                            fixture_type = info.get('fixture_type', 'plumbing fixture')
                            return {
                                'has_enough_info': False,
                                'missing_key': 'issue_type',
                                'next_question': f"What is the issue with your {fixture_type} (e.g., leaking, clogged, broken)?"
                            }
                        else:
                            return {
                                'has_enough_info': False,
                                'missing_key': 'issue_type',
                                'next_question': "What is the issue with your aircon unit (e.g., not cooling, noise, leaking)?"
                            }
            
            # If we have all required fields, we have enough info
            return {
                'has_enough_info': True,
                'missing_key': None,
                'next_question': None
            }
        
        # If we don't have a category yet, use the LLM for more general analysis
        llm = get_entity_extraction_llm()
        
         # Create a system prompt for determining missing information
        system_prompt = """You are a service quotation assistant. Determine what information is missing to provide an accurate quotation.

For different service categories, we need different information:
- Aircon Servicing: unit_type, service_type, hp_size, quantity
- Aircon Installation: unit_type, hp_size, brand, quantity
- Aircon Repair: unit_type, issue_type, quantity
- Plumber: fixture_type, issue_type, quantity

Your task is to:
1. Analyze the information we already have
2. Determine what critical information is missing
3. Generate a natural question to ask the user to get this information

Return your response as a JSON object with:
- has_enough_info: true/false
- missing_key: the key of the missing information (if any)
- next_question: the question to ask the user (if needed)
"""
        
        # Create the prompt
        prompt = f"Determine what information is missing from this context: {json.dumps(info)}"
        
        # Invoke the LLM
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the JSON from the response
        response_text = response.content
        
        # Try to find and parse JSON in the response
        try:
            # Look for JSON pattern
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                # If no JSON pattern found, try to parse the whole response
                result = json.loads(response_text)
            
            # Ensure the result has the required fields
            if 'has_enough_info' not in result:
                result['has_enough_info'] = False
            
            if 'missing_key' not in result and not result['has_enough_info']:
                result['missing_key'] = None
            
            if 'next_question' not in result and not result['has_enough_info']:
                result['next_question'] = "Could you provide more details about your service request?"
            
            return result
        
        except json.JSONDecodeError:
            # If JSON parsing fails, extract information manually
            logger.warning(f"Failed to parse JSON from LLM response: {response_text}")
            
            # Default response
            result = {
                'has_enough_info': False,
                'missing_key': None,
                'next_question': "Could you provide more details about your service request?"
            }
            
            # Try to extract information from the text
            if "has enough information" in response_text.lower() or "sufficient information" in response_text.lower():
                result['has_enough_info'] = True
            
            # Extract missing key
            missing_key_match = re.search(r"missing[_\s]key[:\s]+([a-zA-Z_]+)", response_text, re.IGNORECASE)
            if missing_key_match:
                result['missing_key'] = missing_key_match.group(1)
            
            # Extract next question
            next_question_match = re.search(r"next[_\s]question[:\s]+(.*?)(?:\n|$)", response_text, re.IGNORECASE)
            if next_question_match:
                result['next_question'] = next_question_match.group(1).strip()
            elif "?" in response_text:
                # Find the first question in the text
                question_match = re.search(r"([^.!?]+\?)", response_text)
                if question_match:
                    result['next_question'] = question_match.group(1).strip()
            
            return result
    
    except Exception as e:
        logger.error(f"Error determining missing info with LLM: {e}")
        return {
            'has_enough_info': False,
            'missing_key': None,
            'next_question': "Could you provide more details about your service request?"
        }
    
def find_matching_services(info: Dict) -> List[Dict]:
    """Find services that match the given information using fuzzy matching"""
    try:
        # Get data analysis
        df = get_quotation_data()
        
        # Extract key information
        category = info.get('category')
        if not category:
            return []
        
        # Filter by category
        category_df = df[df['category'] == category]
        if category_df.empty:
            return []
        
        # Prepare search terms based on the information we have
        search_terms = []
        
        # Add unit type if available
        if 'unit_type' in info and info['unit_type']:
            unit_type = info['unit_type'].lower()
            if unit_type == 'wall':
                search_terms.append('wall mounted')
            elif unit_type == 'ceiling':
                search_terms.append('ceiling')
            elif unit_type == 'cassette':
                search_terms.append('cassette')
        
        # Add service type if available
        if 'service_type' in info and info['service_type']:
            service_type = info['service_type'].lower()
            if service_type == 'basic_servicing':
                search_terms.append('basic servicing')
            elif service_type == 'chemical_cleaning':
                search_terms.append('chemical')
            elif service_type == 'gas_topup':
                search_terms.append('gas')
        
        # Add HP size if available - improved non-hardcoded approach
        if 'hp_size' in info and info['hp_size']:
            requested_hp = float(info['hp_size'])
            
            # First, look for exact matches
            exact_match_found = False
            for description in category_df['item_description'].tolist():
                # Look for exact HP match (e.g., "3.0HP")
                exact_matches = re.findall(r'(\d+\.?\d*)HP(?!\s+TO)', description, re.IGNORECASE)
                for match in exact_matches:
                    match_hp = float(match)
                    if abs(match_hp - requested_hp) < 0.1:  # Allow small difference for rounding
                        search_terms.append(f"{match}HP")
                        exact_match_found = True
                        break
            
            # If no exact match, look for ranges
            if not exact_match_found:
                for description in category_df['item_description'].tolist():
                    # Look for HP ranges (e.g., "3.0HP TO 4.0HP")
                    range_match = re.search(r'(\d+\.?\d*)HP\s+TO\s+(\d+\.?\d*)HP', description, re.IGNORECASE)
                    if range_match:
                        range_start = float(range_match.group(1))
                        range_end = float(range_match.group(2))
                        if range_start <= requested_hp <= range_end:
                            range_term = f"{range_match.group(1)}HP TO {range_match.group(2)}HP"
                            if range_term not in search_terms:
                                search_terms.append(range_term)
            
            # If still no match, add the requested HP as a search term
            if not search_terms or not exact_match_found:
                # Format with one decimal place
                formatted_hp = f"{requested_hp:.1f}".rstrip('0').rstrip('.') if '.' in f"{requested_hp:.1f}" else f"{requested_hp:.0f}"
                search_terms.append(f"{formatted_hp}HP")
        
        # Add brand if available
        if 'brand' in info and info['brand']:
            search_terms.append(info['brand'])
        
        # Add fixture type if available
        if 'fixture_type' in info and info['fixture_type']:
            search_terms.append(info['fixture_type'])
        
        # Add issue type if available
        if 'issue_type' in info and info['issue_type']:
            search_terms.append(info['issue_type'])
        
        # If no search terms, return empty list
        if not search_terms:
            return []
        
        # Calculate match scores for each service
        matches = []
        for _, row in category_df.iterrows():
            description = row['item_description'].lower()
            
            # Calculate match score based on search terms
            match_score = 0
            for term in search_terms:
                if term.lower() in description:
                    match_score += 100 / len(search_terms)
            
            # Add fuzzy matching for better results
            if match_score == 0:
                # Try fuzzy matching
                for term in search_terms:
                    fuzzy_score = fuzz.partial_ratio(term.lower(), description)
                    match_score += fuzzy_score / len(search_terms)
            
            # Only consider matches with a score above 30
            if match_score >= 30:
                matches.append({
                    'invoice_no': row['invoice_no'],
                    'category': row['category'],
                    'description': row['item_description'],
                    'unit_price': float(row['unit_price']),
                    'subtotal': float(row['subtotal']),
                    'tax': float(row['tax']),
                    'total': float(row['total']),
                    'match_score': match_score
                })
        
        # Sort matches by score (highest first)
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        
        return matches
    
    except Exception as e:
        logger.error(f"Error finding matching services: {e}")
        return []

def generate_quotation(service: Dict, quantity: int = 1) -> str:
    """Generate a quotation based on the service information and quantity"""
    description = service['description']
    unit_price = service['unit_price']
    subtotal = unit_price * quantity
    tax = subtotal * 0.08
    total = subtotal + tax
    
    quotation = f"""SERVICE QUOTATION
------------------
Service Description: {description}
Quantity: {quantity}
Unit Price (RM): {unit_price:.2f}
Subtotal: {subtotal:.2f}
Tax (8%): {tax:.2f}
Total: {total:.2f}

This quotation is based on our database of similar services.
Additional charges may apply depending on specific requirements.
"""
    
    return quotation

def is_problematic_response(response_text):
    """Check if the response is problematic (raw data, code, etc.)"""
    if not response_text:
        return True
        
    # Check for raw dataframe output
    if "rows x" in response_text and any(col in response_text for col in ["invoice_no", "company_name", "item_description"]):
        return True
        
    # Check for code snippets
    if "df[" in response_text or "print(" in response_text or ".mean()" in response_text:
        return True
        
    # Check for just numbers
    if response_text.strip().replace(".", "").isdigit():
        return True
        
    # Check for "Average" calculations
    if "Average" in response_text and any(term in response_text for term in ["Price", "Unit Price", "Subtotal", "Total"]):
        return True
        
    return False

def handle_direct_response(message: str, last_question_type: str) -> Dict:
    """Handle direct responses to specific questions"""
    message_lower = message.lower().strip()
    
    # Handle direct answers to unit_type questions
    if last_question_type == 'unit_type':
        if message_lower in ['wall', 'wall mounted', 'wall-mounted']:
            return {'unit_type': 'wall'}
        elif message_lower in ['window', 'window unit', 'window-unit', 'window type']:
            return {'unit_type': 'window'}
        elif message_lower in ['ceiling', 'ceiling mounted', 'ceiling-mounted']:
            return {'unit_type': 'ceiling'}
        elif message_lower in ['cassette', 'cassette type', 'cassette-type']:
            return {'unit_type': 'cassette'}
        elif message_lower in ['split', 'split unit', 'split-unit']:
            return {'unit_type': 'wall'}  # Most split units are wall-mounted
    
    # Handle direct answers to service_type questions
    elif last_question_type == 'service_type':
        if any(term in message_lower for term in ['basic', 'general', 'normal', 'regular', 'standard']):
            return {'service_type': 'basic_servicing'}
        elif any(term in message_lower for term in ['chemical', 'deep', 'thorough', 'complete']):
            return {'service_type': 'chemical_cleaning'}
        elif any(term in message_lower for term in ['gas', 'top up', 'refill', 'recharge']):
            return {'service_type': 'gas_topup'}
        elif any(term in message_lower for term in ['install', 'installation', 'setup', 'set up']):
            return {'service_type': 'installation'}
        elif any(term in message_lower for term in ['repair', 'fix', 'troubleshoot']):
            return {'service_type': 'repair'}
    
    # Handle direct answers to hp_size questions
    elif last_question_type == 'hp_size':
        # Check for HP in the message
        hp_match = re.search(r'(\d+(\.\d+)?)\s*hp', message_lower)
        if hp_match:
            return {'hp_size': hp_match.group(1)}
        # Check if the message is just a number
        elif re.match(r'^\d+(\.\d+)?$', message_lower):
            return {'hp_size': message_lower}
    
    # Handle direct answers to quantity questions
    elif last_question_type == 'quantity':
        # Check if the message is just a number
        if re.match(r'^\d+$', message_lower):
            return {'quantity': int(message_lower)}
        # Check for quantity words
        quantity_words = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        for word, value in quantity_words.items():
            if word in message_lower:
                return {'quantity': value}
    
    # Handle direct answers to brand questions
    elif last_question_type == 'brand':
        common_brands = ['daikin', 'panasonic', 'samsung', 'lg', 'mitsubishi', 'hitachi', 'toshiba', 'sharp', 'carrier']
        for brand in common_brands:
            if brand in message_lower:
                return {'brand': brand}
    
    # Handle direct answers to fixture_type questions
    elif last_question_type == 'fixture_type':
        if any(term in message_lower for term in ['toilet', 'wc', 'bathroom']):
            return {'fixture_type': 'toilet'}
        elif any(term in message_lower for term in ['sink', 'basin', 'tap', 'faucet']):
            return {'fixture_type': 'sink'}
        elif any(term in message_lower for term in ['pipe', 'piping', 'water pipe', 'drain']):
            return {'fixture_type': 'pipe'}
        elif any(term in message_lower for term in ['water heater', 'heater', 'hot water']):
            return {'fixture_type': 'water_heater'}
        elif any(term in message_lower for term in ['water tank', 'tank', 'storage']):
            return {'fixture_type': 'water_tank'}
        
    elif last_question_type == 'issue_type':
        if any(term in message_lower for term in ['leak', 'leaking', 'water leak']):
            return {'issue_type': 'leaking'}
        elif any(term in message_lower for term in ['clog', 'clogged', 'blocked', 'blockage']):
            return {'issue_type': 'clogged'}
        elif any(term in message_lower for term in ['broken', 'damaged', 'not working']):
            return {'issue_type': 'broken'}
        elif any(term in message_lower for term in ['not cooling', 'no cool', 'warm air']):
            return {'issue_type': 'not_cooling'}
        elif any(term in message_lower for term in ['noise', 'noisy', 'loud', 'sound']):
            return {'issue_type': 'noise'}
    
    # No direct match found
    return {}

def generate_dynamic_response(query: str, context: Dict = None) -> Dict:
    """
    Generate a dynamic response based on the query and context.
    
    Returns a dictionary with:
    - response: The response text
    - has_quotation: Whether the response contains a quotation
    - needs_more_info: Whether we need more information from the user
    - next_question: The next question to ask if we need more info
    """
    try:
        # Extract information from the query
        if context:
            # Update context with new information from the query
            new_entities = extract_entities_with_llm(query, context)
            
            # Only update with new information, don't overwrite existing context
            for key, value in new_entities.items():
                if value and (key not in context or not context[key]):
                    context[key] = value
                    logger.info(f"Updated context {key} = {value}")
            
            info = context
        else:
            info = extract_entities_with_llm(query)
        
        # Check if we have enough information to provide a quotation
        missing_info_result = determine_missing_info_with_llm(info)
        has_enough_info = missing_info_result.get('has_enough_info', False)
        next_question = missing_info_result.get('next_question', "Could you provide more details?")
        missing_key = missing_info_result.get('missing_key')
        
        # Store the last question type for better context tracking
        if missing_key and context:
            context['last_question_type'] = missing_key
        
        # If we don't have enough information, ask for more
        if not has_enough_info:
            return {
                "response": next_question,
                "has_quotation": False,
                "needs_more_info": True,
                "next_question": next_question,
                "missing_key": missing_key
            }
        
        # Find matching services
        matches = find_matching_services(info)
        
        # If we have matches, generate a quotation
        if matches:
            # Get the best match
            best_match = matches[0]
            
            # Only proceed if the match score is good enough
            if best_match['match_score'] < 40:
                # If match score is too low, ask for more specific information
                return {
                    "response": f"I found some potential matches, but I'm not confident they meet your requirements. Could you provide more specific details about the {info.get('category', 'service')} you need?",
                    "has_quotation": False,
                    "needs_more_info": True,
                    "next_question": f"Could you provide more specific details about the {info.get('category', 'service')} you need?"
                }
            
            # Generate quotation
            quantity = info.get('quantity', 1)  # Default to 1 if not specified
            if isinstance(quantity, str) and quantity.isdigit():
                quantity = int(quantity)
            elif not isinstance(quantity, int):
                quantity = 1
                
            quotation = generate_quotation(best_match, quantity)
            
            # Add explanation of the match
            response = f"""Based on your requirements, I found a matching service:

{quotation}

This quotation is for \n {best_match['description']} with a match score of {int(best_match['match_score'])}%.
"""
            
            # If there are other close matches, mention them
            if len(matches) > 1:
                response += "\nOther similar services you might consider:\n"
                for i, match in enumerate(matches[1:3], 1):  # Show up to 2 more matches
                    response += f"{i}. {match['description']} - RM {match['unit_price']:.2f} (match score: {int(match['match_score'])}%)\n"
            
            return {
                "response": response,
                "has_quotation": True,
                "needs_more_info": False,
                "next_question": None
            }
        else:
            # If no matches, provide a generic response based on the category
            category = info.get('category')
            
            if category == 'Aircon Servicing':
                analysis = analyze_data()
                category_data = analysis['category_analysis'].get(category, {})
                price_range = category_data.get('price_range', {})
                
                response = f"""I couldn't find an exact match for your requirements, but here's a general price range for aircon servicing:

Price range: RM {price_range.get('min', 30):.2f} - RM {price_range.get('max', 340):.2f}

To provide a more accurate quotation, could you please provide more specific details about:
1. The exact type and model of your aircon unit
2. The specific service you need
3. Any additional requirements or conditions
"""
            elif category == 'Aircon Installation':
                    analysis = analyze_data()
                    category_data = analysis['category_analysis'].get(category, {})
                    price_range = category_data.get('price_range', {})
                
                    response = f"""I couldn't find an exact match for your requirements, but here's a general price range for aircon installation:

Price range: RM {price_range.get('min', 550):.2f} - RM {price_range.get('max', 4500):.2f}

To provide a more accurate quotation, could you please provide more specific details about:
1. The exact type and model of aircon you want to install
2. The installation location and conditions
3. Any additional requirements (e.g., extra piping, concealment work)
"""
            elif category == 'Aircon Repair':
                    analysis = analyze_data()
                    category_data = analysis['category_analysis'].get(category, {})
                    price_range = category_data.get('price_range', {})
                    response = f"""I couldn't find an exact match for your requirements, but here's a general price range for aircon repair:

Price range: RM {price_range.get('min', 80):.2f} - RM {price_range.get('max', 3850):.2f}

To provide a more accurate quotation, could you please provide more specific details about:
1. The exact issue with your aircon unit
2. The type of unit and its model
3. Any additional requirements or conditions
"""
            elif category == 'Plumber':
                analysis = analyze_data()
                category_data = analysis['category_analysis'].get(category, {})
                price_range = category_data.get('price_range', {})
                response = f"""I couldn't find an exact match for your requirements, but here's a general price range for plumbing services:

Price range: RM {price_range.get('min', 80):.2f} - RM {price_range.get('max', 3850):.2f}

To provide a more accurate quotation, could you please provide more specific details about:
1. The exact plumbing issue or service you need
2. The fixtures involved (toilet, sink, pipes, etc.)
3. The severity or complexity of the issue
"""
            else:
                response = """I couldn't find a match for your requirements. Could you please provide more specific details about the service you need?

For example:
- For aircon services: type of unit, service needed, horsepower
- For plumbing services: type of fixture, issue, specific requirements
"""
            
            return {
                "response": response,
                "has_quotation": False,
                "needs_more_info": True,
                "next_question": "Could you please provide more specific details?"
            }
    
    except Exception as e:
        logger.error(f"Error generating dynamic response: {e}")
        return {
            "response": "I apologize, but I encountered an error processing your request. Could you please try again with more specific details?",
            "has_quotation": False,
            "needs_more_info": True,
            "next_question": "Could you please provide more specific details about the service you need?"
        }

def detect_and_handle_off_topic_with_llm(message, context):
    """
    Use LLM to detect if a message is off-topic and generate an appropriate response
    
    Returns:
        Tuple[bool, str]: (is_off_topic, response_if_off_topic)
    """
    try:
        # First check if this could be an information request
        user_intent = classify_user_intent(message, context)
        if user_intent in ["information_request", "price_info", "popular_services_info"]:
            # Information requests are on-topic
            return False, None
        
        # Get the LLM
        llm = get_entity_extraction_llm()
        
        # Create context information for the LLM
        context_info = ""
        if context:
            context_info = "Current conversation context:\n"
            for key, value in context.items():
                if key not in ['chat_history', 'last_query', 'information_gathering_stage', 'missing_info', 'last_question_type'] and value:
                    context_info += f"- {key}: {value}\n"
            
            # Add last few messages for context
            if context.get('chat_history'):
                context_info += "\nRecent conversation:\n"
                for i, (q, a) in enumerate(context.get('chat_history', [])[-2:]):
                    context_info += f"User: {q}\nAssistant: {a}\n"
        
        # Create a system prompt for off-topic detection and response
        system_prompt = f"""You are a service quotation assistant for aircon and plumbing services. 
Your task is to determine if the user's message is on-topic or off-topic, and provide an appropriate response.

{context_info}

You can help with:
- Aircon servicing (basic or chemical cleaning)
- Aircon installation (various brands and sizes)
- Aircon repairs
- Plumbing services (toilets, sinks, pipes, etc.)

First, determine if the message is on-topic or off-topic for these services.
Then, if it's off-topic, generate a helpful response that:
1. Acknowledges the off-topic message
2. Explains your purpose as a service quotation assistant
3. Guides the user back to the topic of service quotations
4. If there was an ongoing conversation about a specific service, remind them of it

Return your response as a JSON object with:
- "is_off_topic": true/false
- "response": your helpful response if off-topic, or null if on-topic
"""
        
        # Create the prompt
        prompt = f"User message: {message}"
        
        # Invoke the LLM
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the JSON from the response
        response_text = response.content
        
        # Try to find and parse JSON in the response
        try:
            # Look for JSON pattern
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                # If no JSON pattern found, try to parse the whole response
                result = json.loads(response_text)
            
            is_off_topic = result.get('is_off_topic', False)
            response_text = result.get('response', None)
            
            return is_off_topic, response_text
        
        except json.JSONDecodeError:
            # If JSON parsing fails, extract information manually
            logger.warning(f"Failed to parse JSON from LLM response: {response_text}")
            
            # Check if the response indicates off-topic
            is_off_topic = "off-topic" in response_text.lower()
            
            # If it's off-topic, use the whole response as the response text
            if is_off_topic:
                # Clean up the response to remove JSON-like formatting
                cleaned_response = re.sub(r'["{}\[\]]', '', response_text)
                cleaned_response = re.sub(r'is_off_topic:\s*true,?\s*response:', '', cleaned_response, flags=re.IGNORECASE)
                return True, cleaned_response.strip()
            
            return False, None
    
    except Exception as e:
        logger.error(f"Error in detect_and_handle_off_topic_with_llm: {e}")
        # Default to on-topic in case of errors
        return False, None

def is_affirmative_response(message: str) -> bool:
    """Check if a message is an affirmative response using LLM"""
    try:
        # Get the LLM
        llm = get_entity_extraction_llm()
        
        # Create a system prompt for detecting affirmative responses
        system_prompt = """You are a response classifier. Your task is to determine if a message is an affirmative response.

Examples of affirmative responses include: yes, yeah, yep, sure, ok, okay, I do, I would, please, of course, definitely, absolutely, certainly.

Return ONLY a JSON object with a single field "is_affirmative" set to true or false.
"""
        
        # Create the prompt
        prompt = f"Is this message an affirmative response? Message: '{message}'"
        
        # Invoke the LLM
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the JSON from the response
        response_text = response.content
        
        # Try to find and parse JSON in the response
        try:
            # Look for JSON pattern
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                # If no JSON pattern found, try to parse the whole response
                result = json.loads(response_text)
            
            return result.get('is_affirmative', False)
        
        except json.JSONDecodeError:
            # If JSON parsing fails, check for "true" or "yes" in the response
            return "true" in response_text.lower() or "yes" in response_text.lower()
    
    except Exception as e:
        logger.error(f"Error in is_affirmative_response: {e}")
        # Fall back to simple pattern matching in case of errors
        message_lower = message.lower().strip()
        affirmative_phrases = ["yes", "yeah", "yep", "sure", "ok", "okay"]
        return any(phrase in message_lower for phrase in affirmative_phrases)

def is_negative_response(message: str) -> bool:
    """Check if a message is a negative response using LLM"""
    try:
        # Get the LLM
        llm = get_entity_extraction_llm()
        
        # Create a system prompt for detecting negative responses
        system_prompt = """You are a response classifier. Your task is to determine if a message is a negative response.

Examples of negative responses include: no, nope, nah, not, don't, dont, I don't, I dont, no thanks, no thank you.

Return ONLY a JSON object with a single field "is_negative" set to true or false.
"""
        
        # Create the prompt
        prompt = f"Is this message a negative response? Message: '{message}'"
        
        # Invoke the LLM
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the JSON from the response
        response_text = response.content
        
        # Try to find and parse JSON in the response
        try:
            # Look for JSON pattern
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                # If no JSON pattern found, try to parse the whole response
                result = json.loads(response_text)
            
            return result.get('is_negative', False)
        
        except json.JSONDecodeError:
            # If JSON parsing fails, check for "true" or "yes" in the response
            return "true" in response_text.lower() or "yes" in response_text.lower()
    
    except Exception as e:
        logger.error(f"Error in is_negative_response: {e}")
        # Fall back to simple pattern matching in case of errors
        message_lower = message.lower().strip()
        negative_phrases = ["no", "nope", "nah", "not", "don't", "dont"]
        return any(phrase in message_lower for phrase in negative_phrases)

def is_confirmation_message(message: str) -> bool:
    """Check if a message is confirming a quotation using LLM"""
    try:
        # Get the LLM
        llm = get_entity_extraction_llm()
        
        # Create a system prompt for detecting confirmation messages
        system_prompt = """You are a response classifier. Your task is to determine if a message is confirming a quotation or proposal.

Examples of confirmation messages include: yes, yeah, yep, sure, ok, okay, confirm, I confirm, sounds good, that works, proceed, 
go ahead, I accept, accept, agreed, I agree, that's fine, that is fine, looks good, good.

Return ONLY a JSON object with a single field "is_confirmation" set to true or false.
"""
        
        # Create the prompt
        prompt = f"Is this message confirming a quotation? Message: '{message}'"
        
        # Invoke the LLM
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the JSON from the response
        response_text = response.content
        
        # Try to find and parse JSON in the response
        try:
            # Look for JSON pattern
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                # If no JSON pattern found, try to parse the whole response
                result = json.loads(response_text)
            
            return result.get('is_confirmation', False)
        
        except json.JSONDecodeError:
            # If JSON parsing fails, check for "true" or "yes" in the response
            return "true" in response_text.lower() or "yes" in response_text.lower()
    
    except Exception as e:
        logger.error(f"Error in is_confirmation_message: {e}")
        # Fall back to simple pattern matching in case of errors
        message_lower = message.lower().strip()
        confirmation_phrases = ["yes", "confirm", "accept", "agree", "proceed", "ok", "okay"]
        return any(phrase in message_lower for phrase in confirmation_phrases)
   
def process_message(message: str, session_id: str = "default", system_prompt: str = None):
    """Process a message and generate a response"""
    global _conversation_context
    
    try:
        # Log the incoming request
        logger.info(f"Processing message for session {session_id}: {message}")
        
        # Check for reset command
        if message.lower() == 'reset':
            if session_id in _conversation_context:
                del _conversation_context[session_id]
            return {
                "response": "Conversation has been reset. How can I help you today?",
                "display_quotation": False,
                "quotation": None
            }
        
        # Get or initialize conversation context
        if session_id not in _conversation_context:
            _conversation_context[session_id] = {
                'category': None,
                'unit_type': None,
                'service_type': None,
                'hp_size': None,
                'brand': None,
                'fixture_type': None,
                'issue_type': None,
                'quantity': None,
                'chat_history': [],
                'last_query': None,
                'last_question_type': None,
                'information_gathering_stage': True,
                'missing_info': [],
                'last_quotation': None,  # Store the last quotation
                'quotation_confirmed': False,  # Track if quotation is confirmed
                'asked_for_another_quotation': False  # Track if we've asked for another quotation
            }
        
        context = _conversation_context[session_id]
        
        # Determine user intent
        user_intent = classify_user_intent(message, context)
        logger.info(f"Classified user intent: {user_intent}")
        
        # Handle information requests differently
        if user_intent in ["information_request", "price_info", "popular_services_info"]:
            info_result = handle_information_request(message, context)
            
            # Store the interaction in chat history
            context['chat_history'].append((message, info_result["response"]))
            
            return {
                "response": info_result["response"],
                "display_quotation": False,
                "quotation": None
            }
        
        # Check if this is a confirmation of a previous quotation
        if context.get('last_quotation') and not context.get('quotation_confirmed') and is_confirmation_message(message):
            # Mark the quotation as confirmed
            context['quotation_confirmed'] = True
            context['asked_for_another_quotation'] = True
            
            # Get the last quotation
            last_quotation = context.get('last_quotation')
            
            # Create a confirmation response with a follow-up question
            confirmation_response = "Thank you for confirming your quotation. Your service request has been recorded.\n\nWould you like to get a quotation for any other service? Or type 'quit' to finish and download your quotations."
            
            # Update chat history
            context['chat_history'].append((message, confirmation_response))
            
            # Return the confirmation with a flag to display the quotation
            return {
                "response": confirmation_response,
                "display_quotation": True,
                "quotation": last_quotation
            }
        
        # Check if user is responding to "would you like another quotation" question
        if context.get('asked_for_another_quotation') and context.get('quotation_confirmed'):
            # Check if user wants to quit
            if message.lower() in ['quit', 'exit', 'no', 'done', 'finish', 'end']:
                response = "Thank you for using our service! Your quotations are ready for download. If you need anything else in the future, just start a new chat."
                context['chat_history'].append((message, response))
                return {
                    "response": response,
                    "display_quotation": False,
                    "quotation": None
                }
            
            # If user wants another quotation, reset relevant parts of the context
            if is_affirmative_response(message) or message.lower() not in ['quit', 'exit', 'no', 'done', 'finish', 'end']:
                # Keep the chat history but reset the service-specific information
                context['category'] = None
                context['unit_type'] = None
                context['service_type'] = None
                context['hp_size'] = None
                context['brand'] = None
                context['fixture_type'] = None
                context['issue_type'] = None
                context['quantity'] = None
                context['last_quotation'] = None
                context['quotation_confirmed'] = False
                context['asked_for_another_quotation'] = False
                context['information_gathering_stage'] = True
                
                response = "Great! What type of service would you like a quotation for? (e.g., Aircon Servicing, Aircon Installation, Aircon Repair, or Plumber)"
                context['chat_history'].append((message, response))
                return {
                    "response": response,
                    "display_quotation": False,
                    "quotation": None
                }
        
        # Check if message is off-topic using LLM
        is_off_topic, off_topic_response = detect_and_handle_off_topic_with_llm(message, context)
        if is_off_topic and off_topic_response:
            context['chat_history'].append((message, off_topic_response))
            return {
                "response": off_topic_response,
                "display_quotation": False,
                "quotation": None
            }
        
        # For direct answers to specific questions in the quotation flow,
        # make sure we're correctly handling numeric inputs
        if user_intent == "direct_answer" and context.get('information_gathering_stage'):
            if context.get('last_question_type') == 'quantity' and message.strip().isdigit():
                # This is a direct quantity answer, store it properly
                quantity = int(message.strip())
                context['quantity'] = quantity
                logger.info(f"Updated context quantity = {quantity}")
                
            elif context.get('last_question_type') == 'hp_size' and re.match(r'^\d+(\.\d+)?(\s*hp)?$', message.lower()):
                # This is a direct HP size answer
                hp_match = re.search(r'(\d+(\.\d+)?)', message.lower())
                if hp_match:
                    hp_size = hp_match.group(1)
                    context['hp_size'] = hp_size
                    logger.info(f"Updated context hp_size = {hp_size}")
        
        # Extract entities from the message
        new_entities = extract_entities_with_llm(message, context)
        
        # Update context with new entities
        for key, value in new_entities.items():
            if value:  # Only update if the value is not None or empty
                context[key] = value
                logger.info(f"Updated context {key} = {value}")
        
        # Try to generate a dynamic response
        dynamic_result = generate_dynamic_response(message, context)
        
        # If we need more information, return the question
        if dynamic_result['needs_more_info']:
            logger.info(f"Need more information. Next question: {dynamic_result['next_question']}")
            context['information_gathering_stage'] = True
            context['last_query'] = message
            context['chat_history'].append((message, dynamic_result['response']))
            if 'missing_key' in dynamic_result and dynamic_result['missing_key']:
                context['last_question_type'] = dynamic_result['missing_key']
            return {
                "response": dynamic_result['response'],
                "display_quotation": False,
                "quotation": None
            }
        
        # If we have a quotation, store it and return it
        if dynamic_result['has_quotation']:
            logger.info(f"Generated quotation: {dynamic_result['response']}")
            context['information_gathering_stage'] = False
            context['last_query'] = message
            
            # Store the quotation in the context
            context['last_quotation'] = dynamic_result['response']
            
            # Add a prompt to confirm the quotation
            confirmation_prompt = "\n\nIf you would like to proceed with this quotation, please confirm by saying 'Yes' or 'Confirm'."
            full_response = dynamic_result['response'] + confirmation_prompt
            
            context['chat_history'].append((message, full_response))
            
            return {
                "response": full_response,
                "display_quotation": False,
                "quotation": dynamic_result['response']
            }
        
        # If dynamic response didn't work, use the agent as fallback
        try:
            # Get data
            df = get_quotation_data()
            
            # Initialize LLM
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash", 
                api_key=GEMINI_API_KEY,
                temperature=0.2
            )
            
            # Create system prompt
            if not system_prompt:
                system_prompt = get_default_system_prompt()
            
            # Add context-specific instructions to the system prompt
            if context['category']:
                system_prompt += f"\n\nThe user is asking about {context['category']}."
                
                if context['category'] == 'Aircon Servicing' and context['service_type'] == 'chemical_cleaning':
                    system_prompt += " Focus on chemical cleaning services, not basic servicing."
                elif context['category'] == 'Aircon Installation':
                    system_prompt += " Focus on installation services and costs."
                elif context['category'] == 'Aircon Repair':
                    system_prompt += " Focus on repair services and costs."
                elif context['category'] == 'Plumber':
                    system_prompt += " Focus on plumbing-related services and costs."
            
            # Add information about what we already know
            system_prompt += "\n\nInformation gathered so far:"
            for key, value in context.items():
                if key not in ['chat_history', 'last_query', 'information_gathering_stage', 'missing_info', 
                              'last_question_type', 'last_quotation', 'quotation_confirmed', 'asked_for_another_quotation'] and value:
                    system_prompt += f"\n- {key}: {value}"
            
            # Build chat history for context
            chat_history = [SystemMessage(content=system_prompt)] 
            
            for i, (q, a) in enumerate(context.get('chat_history', [])[-3:]):
                chat_history.append(HumanMessage(content=q))
                chat_history.append(SystemMessage(content=a))
            
            # Create agent
            agent = create_pandas_dataframe_agent(
                llm, 
                df,
                verbose=True,
                agent_type="zero-shot-react-description",
                handle_parsing_errors=True,
                max_iterations=3,
                allow_dangerous_code=True
            )
            
            # Enhance the message with instructions based on the context
            enhanced_message = f"""
            {message}
            
            IMPORTANT: 
            1. DO NOT calculate averages or sums across all services.
            2. DO NOT return raw dataframes or code.
            3. DO NOT provide a quotation until you have all necessary details.
            4. Ask follow-up questions to gather all required information.
            5. If you don't have enough information, ask specific questions.
            """
            
            # Add the current message to chat history
            chat_history.append(HumanMessage(content=enhanced_message))
            
            # Invoke the agent
            response = agent.invoke({
                "input": enhanced_message,
                "chat_history": chat_history
            })
            
              # Extract the output text
            if isinstance(response, dict) and 'output' in response:
                response_text = response['output']
            else:
                response_text = str(response)
            
            # Check if the response is problematic
            if is_problematic_response(response_text):
                logger.warning(f"Detected problematic response: {response_text}")
                
                # Try again with more specific instructions
                retry_message = f"""
                {message}
                
                CRITICAL INSTRUCTIONS:
                1. DO NOT show any code, dataframes, or raw data in your response.
                2. DO NOT calculate averages or sums across all services.
                3. DO NOT just return a number.
                4. Instead, ask specific questions to gather more information about what the user needs.
                5. DO NOT provide a quotation until you have all necessary details.
                """
                
                # Retry with more specific instructions
                retry_response = agent.invoke({
                    "input": retry_message,
                    "chat_history": chat_history
                })
                
                # Extract the retry output
                if isinstance(retry_response, dict) and 'output' in retry_response:
                    retry_text = retry_response['output']
                else:
                    retry_text = str(retry_response)
                
                # Check if retry is still problematic
                if is_problematic_response(retry_text):
                    # Fall back to dynamic response
                    response_text = dynamic_result['response']
                else:
                    response_text = retry_text
            
            # Update chat history with the response
            context['chat_history'].append((message, response_text))
            context['last_query'] = message
            
            # Log the final response
            logger.info(f"Final response: {response_text}")
            
            return {
                "response": response_text,
                "display_quotation": False,
                "quotation": None
            }
        except Exception as e:
            logger.error(f"Agent error: {e}")
            
            # Fall back to dynamic response
            return {
                "response": dynamic_result['response'],
                "display_quotation": False,
                "quotation": None
            }
               
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return {
            "response": f"I apologize, but I encountered an error. Could you please try again with more specific details?",
            "display_quotation": False,
            "quotation": None
        }  
    
def get_default_system_prompt():
    """Get the default system prompt based on the data"""
    try:
        # Get data analysis
        analysis = analyze_data()
        
        # Extract key information from the data
        categories = analysis['categories']
        categories_str = ", ".join(categories)
        
        # Create the system prompt
        return f"""You are a quotation generator for services including: {categories_str}.

IMPORTANT INSTRUCTIONS:
1. NEVER calculate averages or sums across all services in the database.
2. NEVER return raw dataframes or code in your response.
3. When asked about pricing, provide PRICE RANGES for specific services.
4. If the user's request is vague, ASK for more specific details.
5. Base your responses on the actual data in the database.
6. DO NOT provide a quotation until you have all necessary details.
7. Ask follow-up questions to gather all required information.

When responding to pricing questions:
1. First determine what service category the user is asking about
2. Then ask specific questions to narrow down the exact service needed
3. Only provide a quotation when you have enough information to match a specific service
4. Format responses as proper quotations when appropriate

For follow-up questions, maintain context from previous messages.
"""
    except Exception as e:
        logger.error(f"Error generating system prompt: {e}")
        return """You are a quotation generator for air-conditioning and plumbing services.

IMPORTANT INSTRUCTIONS:
1. NEVER calculate averages or sums across all services in the database.
2. NEVER return raw dataframes or code in your response.
3. When asked about pricing, provide PRICE RANGES for specific services.
4. If the user's request is vague, ASK for more specific details.
5. Base your responses on the actual data in the database.
6. DO NOT provide a quotation until you have all necessary details.
7. Ask follow-up questions to gather all required information.

When responding to pricing questions:
1. First determine what service category the user is asking about
2. Then ask specific questions to narrow down the exact service needed
3. Only provide a quotation when you have enough information to match a specific service
4. Format responses as proper quotations when appropriate

For follow-up questions, maintain context from previous messages.
"""

def refresh_data():
    """Refresh the data cache"""
    global _df_cache, _data_analysis_cache, _conversation_context, _entity_extraction_llm, _search_llm
    _df_cache = None
    _data_analysis_cache = None
    _conversation_context = {}
    _entity_extraction_llm = None
    _search_llm = None
    get_quotation_data()  # This will refresh the data cache
    analyze_data()  # This will refresh the data analysis
    return "Data cache and analysis refreshed"

def main():
    """Main function to test the chatbot"""
    print("Initializing chatbot...")
    
    # Initialize data
    get_quotation_data()
    analyze_data()
    
    # Create a session ID
    session_id = "test_session"
    
    print("\nChatbot initialized. Type 'exit' to quit, 'reset' to reset the conversation.")
    print("Ask about aircon servicing, installation, repair, or plumbing services.")
    
    while True:
        # Get user input
        user_input = input("\nYou: ")
        
        # Check for exit command
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break
        
        # Process the message
        response = process_message(user_input, session_id)
        
        # Print the response
        print(f"\nChatbot: {response['response']}")

if __name__ == "__main__":
    main()

        