import os
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
import sqlalchemy
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
import pandas as pd

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize LLM outside of functions
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=GEMINI_API_KEY)

def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    """
    Initializes a connection pool for a Cloud SQL instance of Postgres.

    Uses the Cloud SQL Python Connector package.
    """
    # Note: Saving credentials in environment variables is convenient, but not
    # secure - consider a more secure solution such as
    # Cloud Secret Manager (https://cloud.google.com/secret-manager) to help
    # keep secrets safe.

    instance_connection_name = "gaia-capstone08-prd:us-central1:quotemate"  # e.g. 'project:region:instance'
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")

    if not db_user or not db_pass or not db_name:
        raise ValueError("Database credentials (DB_USER, DB_PASS, DB_NAME) are not set in the environment variables.")

    ip_type = IPTypes.PRIVATE if os.environ.get("PRIVATE_IP") else IPTypes.PUBLIC

    # initialize Cloud SQL Python Connector object
    connector = Connector()

    def getconn() -> pg8000.dbapi.Connection:
        conn: pg8000.dbapi.Connection = connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_pass,
            db=db_name,
            ip_type=ip_type,
        )
        return conn

    # The Cloud SQL Python Connector can be used with SQLAlchemy
    # using the 'creator' argument to 'create_engine'
    pool = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        
    )
    return pool

def get_quotation_data_as_df():
    """
    Retrieves quotation data from Cloud SQL and returns it as a pandas DataFrame.

    Returns:
        pandas.DataFrame: DataFrame containing quotation data
        or None if an error occurs
    """
    try:
        # Create the connection pool
        pool = connect_with_connector()
        print("Database connection pool created successfully")
        
        with pool.connect() as db_conn:
            print("Connected successfully to database")
            
            # Query database
            result = db_conn.execute(sqlalchemy.text("SELECT * FROM quotation_data")).fetchall()
            print(f"Query executed successfully, retrieved {len(result)} rows")
            
            # Get column names from the result
            column_names = result[0]._fields if result else []
            
            # Convert to pandas DataFrame
            df = pd.DataFrame(result, columns=column_names)
            print(f"DataFrame created successfully with shape: {df.shape}")
            
        return df
    except Exception as e:
        print(f"Error retrieving quotation data: {e}")
        return None
    
print(os.environ.get("DB_USER"))