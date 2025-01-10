from pymongo import MongoClient, ASCENDING, TEXT
from dotenv import load_dotenv
from urllib.parse import quote_plus
import os
import re

# Load environment variables
load_dotenv()

def get_mongodb_uri():
    uri = os.getenv('MONGODB_URI')
    if not uri:
        print("Error: MONGODB_URI environment variable is not set")
        return None
    
    # Check if the URI needs encoding
    if 'mongodb+srv://' in uri:
        # Extract username, password, and rest of the URI
        match = re.match(r'mongodb\+srv://([^:]+):([^@]+)@(.+)', uri)
        if match:
            username, password, rest = match.groups()
            # Encode username and password
            encoded_username = quote_plus(username)
            encoded_password = quote_plus(password)
            return f'mongodb+srv://{encoded_username}:{encoded_password}@{rest}'
    return uri

def init_database():
    # Get properly encoded MongoDB URI
    mongodb_uri = get_mongodb_uri()
    if not mongodb_uri:
        return

    client = None
    try:
        # Connect to MongoDB
        print("Connecting to MongoDB Atlas...")
        client = MongoClient(mongodb_uri)
        
        # Test connection
        client.admin.command('ping')
        print("Successfully connected to MongoDB Atlas!")
        
        # Get the database
        db = client.get_database()
        print(f"Using database: {db.name}")

        # Create users collection with indexes
        if 'users' not in db.list_collection_names():
            users = db.create_collection('users')
            users.create_index([('username', ASCENDING)], unique=True)
            users.create_index([('email', ASCENDING)], unique=True)
            print("Created users collection with indexes")

        # Create challenges collection with indexes
        if 'challenges' not in db.list_collection_names():
            challenges = db.create_collection('challenges')
            challenges.create_index([('difficulty', ASCENDING)])
            challenges.create_index([('title', TEXT)])
            print("Created challenges collection with indexes")

        # Create submissions collection with indexes
        if 'submissions' not in db.list_collection_names():
            submissions = db.create_collection('submissions')
            submissions.create_index([('user_id', ASCENDING)])
            submissions.create_index([('challenge_id', ASCENDING)])
            submissions.create_index([('timestamp', ASCENDING)])
            print("Created submissions collection with indexes")

        # Create chat_history collection with indexes
        if 'chat_history' not in db.list_collection_names():
            chat_history = db.create_collection('chat_history')
            chat_history.create_index([('user_id', ASCENDING)])
            chat_history.create_index([('timestamp', ASCENDING)])
            print("Created chat_history collection with indexes")

        print("Database initialization completed successfully!")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed")

if __name__ == "__main__":
    init_database() 