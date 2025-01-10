from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import bcrypt
import google.generativeai as genai
from datetime import datetime
from bson.objectid import ObjectId
import json
from werkzeug.security import generate_password_hash

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MONGODB_URI'] = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/codebuddy')
app.config['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')

# Initialize extensions
Session(app)
csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

# Initialize MongoDB
try:
    client = MongoClient(app.config['MONGODB_URI'])
    # Test the connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB!")
    print(f"Database name: {client.get_database().name}")
    db = client.get_database()
except Exception as e:
    print(f"Error connecting to MongoDB: {str(e)}")
    raise e

# Initialize Gemini AI
gemini_api_key = os.getenv('GEMINI_API_KEY')
if not gemini_api_key:
    print("Warning: GEMINI_API_KEY is not set!")
else:
    print(f"Gemini API Key found: {gemini_api_key[:8]}...")
    genai.configure(api_key=gemini_api_key)
    
    # List available models
    print("Available Gemini models:")
    for m in genai.list_models():
        print(f"- {m.name}")

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('code_buddy.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user exists
        if db.users.find_one({'$or': [{'username': username}, {'email': email}]}):
            return jsonify({'error': 'Username or email already exists'}), 400
        
        # Hash password using bcrypt
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create user document
        user = {
            'username': username,
            'email': email,
            'password': hashed,
            'challenges_attempted': 0,
            'correct_solutions': 0,
            'incorrect_solutions': 0,
            'current_streak': 0
        }
        
        result = db.users.insert_one(user)
        session['user_id'] = str(result.inserted_id)
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)

        user = db.users.find_one({'username': username})
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            session['user_id'] = str(user['_id'])
            if remember:
                session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            return jsonify({'error': 'Invalid username or password'}), 401

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = db.users.find_one({'_id': session['user_id']})
    return render_template('code_buddy.html', user=user)

@app.route('/api/chat', methods=['POST'])
@limiter.limit("50 per hour")
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    message = request.json.get('message')
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    try:
        # Check if this is a challenge request
        is_challenge_request = any(keyword in message.lower() for keyword in [
            'give me a challenge', 'new challenge', 'coding challenge',
            'practice problem', 'give me a problem', 'next challenge'
        ])

        # If it's a challenge request, increment challenges_attempted
        if is_challenge_request:
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$inc': {'challenges_attempted': 1}}
            )

        # Create a coding-focused context for Gemini
        if is_challenge_request:
            context = """You are a coding challenge generator. Generate a programming challenge for any coding language that the user asks for that:
            1. Is clear and concise
            2. Has a specific goal
            3. Includes test cases
            4. Is suitable for practice
            
            Generate a challenge and format your response EXACTLY as shown below:
            {
                "id": "challenge_X",
                "title": "Challenge Title",
                "description": "Clear description of what needs to be done",
                "template": "def solution(param1, param2):\\n    # Write your solution here\\n    pass",
                "test_cases": [
                    {
                        "input": {"param1": 1, "param2": 2},
                        "expected": 3
                    },
                    {
                        "input": {"param1": -1, "param2": 1},
                        "expected": 0
                    }
                ]
            }
            
            Make sure:
            1. The challenge is appropriate for learning
            2. The template includes proper function signature and docstring
            3. Test cases are valid JSON (use strings for dictionary keys)
            4. All JSON fields are properly formatted
            5. No additional text before or after the JSON object
            6. All values in test cases must be converted to JSON format
               - Use strings for dictionary keys
               - Use arrays [] instead of tuples ()
               - Use null instead of None
               - Use true/false instead of True/False"""
        else:
            context = """You are an expert programming tutor. Your role is to:
            1. Answer coding questions clearly and concisely
            2. Provide code examples when relevant
            3. Explain concepts in a beginner-friendly way
            4. Help debug code issues
            5. Suggest best practices and improvements
            6. Don't give direct solutions to challenges
            
            Keep responses focused on programming and development.
            Format code examples with proper indentation.
            Use markdown code blocks with language specification when sharing code examples."""
        
        # Initialize Gemini model
        try:
            print("Initializing Gemini 1.5 Flash model...")
            model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            print(f"Error initializing model: {str(e)}")
            raise e
        
        # Combine context and user message
        prompt = f"{context}\n\nUser message: {message}"
        
        print(f"\n=== CHAT PROMPT ===")
        print(prompt)
        print("==================\n")
        
        # Generate response
        response = model.generate_content(prompt)
        
        if not response or not response.text:
            print("Empty response from Gemini API")
            return jsonify({
                'error': 'Empty response from AI',
                'success': False
            }), 500
            
        print(f"\n=== GEMINI RESPONSE ===")
        print(response.text)
        print("======================\n")
        
        # If this was a challenge request, try to parse the challenge
        if is_challenge_request:
            try:
                import json
                # Clean the response text and parse JSON
                clean_response = response.text.strip().replace('```json', '').replace('```', '')
                challenge_data = json.loads(clean_response)
                
                # Validate required fields
                required_fields = ['id', 'title', 'description', 'template', 'test_cases']
                for field in required_fields:
                    if field not in challenge_data:
                        raise ValueError(f"Missing required field: {field}")
                
                # Ensure test_cases is a list
                if not isinstance(challenge_data['test_cases'], list):
                    raise ValueError("test_cases must be a list")
                
                # Save the challenge to the database
                db.challenges.update_one(
                    {'id': challenge_data['id']},
                    {'$set': challenge_data},
                    upsert=True
                )
                
                return jsonify({
                    'response': f"Here's your challenge: {challenge_data['title']}\n\n{challenge_data['description']}",
                    'challenge': challenge_data,
                    'success': True
                })
            except json.JSONDecodeError as e:
                print(f"Error parsing challenge JSON: {str(e)}")
                print(f"Raw response: {clean_response}")
                # Instead of returning error, return the raw response as a regular chat message
                return jsonify({
                    'response': response.text,
                    'success': True
                })
            except Exception as e:
                print(f"Error processing challenge: {str(e)}")
                # Instead of returning error, return the raw response as a regular chat message
                return jsonify({
                    'response': response.text,
                    'success': True
                })
        
        # Save chat history
        chat_entry = {
            'user_id': session['user_id'],
            'message': message,
            'response': response.text,
            'timestamp': datetime.utcnow()
        }
        db.chat_history.insert_one(chat_entry)
        
        return jsonify({
            'response': response.text,
            'success': True
        })
    except Exception as e:
        print(f"Chat error: {str(e)}")
        error_message = str(e)
        if "API key not available" in error_message:
            error_message = "API key configuration error. Please check your settings."
        return jsonify({
            'error': 'Failed to generate response',
            'details': error_message,
            'success': False
        }), 500

@app.route('/api/submit-solution', methods=['POST'])
@limiter.limit("20 per hour")
def submit_solution():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    code = request.json.get('code')
    challenge_id = request.json.get('challenge_id')
    
    if not code or not challenge_id:
        return jsonify({
            'status': 'error',
            'message': 'Code and challenge_id are required'
        }), 400

    try:
        # Get the challenge from the database
        challenge = db.challenges.find_one({'id': challenge_id})
        if not challenge:
            return jsonify({
                'status': 'error',
                'message': 'Challenge not found'
            }), 404

        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create evaluation prompt with strict formatting instructions
        evaluation_prompt = f"""You are a code assessment expert. Evaluate the following code solution for this programming challenge.
        
Challenge/Question:
{challenge['description']}

Submitted Code:
```
{code}
```

Test Cases:
{challenge['test_cases']}

Evaluate the code and provide your response in STRICT JSON format as shown below.
DO NOT include any other text, ONLY the JSON object.

{{
    "is_correct": true or false,
    "message": "A brief one-line explanation of the assessment result",
    "feedback": "Detailed feedback about what's good and what could be improved",
    "step_by_step_solution": "Step-by-step solution if the code is incorrect, otherwise null",
    "right_code": "If the submitted solution is incorrect, provide the correct code solution, the programming language should be the same as the submitted code. Otherwise null"
}}

Focus on:
1. Correctness - Does it solve the problem and pass all test cases?
2. Efficiency - Is it an efficient solution?
3. Style - Is it well-written and following best practices?
4. Edge cases - Does it handle edge cases?

If the solution is incorrect, make sure to provide a working solution in the right_code field.
The right_code should be clean, efficient, and well-commented Python code.

IMPORTANT: Your response must be a valid JSON object and nothing else."""

        # Log the evaluation prompt
        print("\n=== EVALUATION PROMPT ===")
        print(evaluation_prompt)
        print("========================\n")

        # Get evaluation from Gemini
        print("Sending evaluation request to Gemini...")
        response = model.generate_content(evaluation_prompt)
        
        if not response or not response.text:
            raise Exception("Empty response from AI")
            
        # Log the raw response
        print("\n=== RAW GEMINI RESPONSE ===")
        print(response.text)
        print("===========================\n")
        
        # Clean the response text to ensure it's valid JSON
        response_text = response.text.strip()
        # Remove any markdown code block markers if present
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        try:
            # Parse the response
            import json
            evaluation = json.loads(response_text)
            
            # Validate required fields
            required_fields = ['is_correct', 'message', 'feedback']
            for field in required_fields:
                if field not in evaluation:
                    raise ValueError(f"Missing required field: {field}")
            
            # Ensure proper types
            evaluation['is_correct'] = bool(evaluation['is_correct'])
            evaluation['message'] = str(evaluation['message'])
            evaluation['feedback'] = str(evaluation['feedback'])
            evaluation['step_by_step_solution'] = str(evaluation.get('step_by_step_solution', '')) if evaluation.get('step_by_step_solution') else None
            evaluation['right_code'] = str(evaluation.get('right_code', '')) if evaluation.get('right_code') and not evaluation['is_correct'] else None
            
            # Log the processed evaluation
            print("\n=== PROCESSED EVALUATION ===")
            print(json.dumps(evaluation, indent=2))
            print("===========================\n")
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")
            # Create a formatted response from unstructured text
            evaluation = {
                "is_correct": False,
                "message": "Unable to parse assessment result",
                "feedback": response_text[:500],  # Use first 500 chars as feedback
                "step_by_step_solution": None,
                "right_code": None
            }
        except Exception as e:
            print(f"Error processing evaluation: {str(e)}")
            evaluation = {
                "is_correct": False,
                "message": "Error processing assessment",
                "feedback": str(e),
                "step_by_step_solution": None,
                "right_code": None
            }
        
        # Save submission with evaluation
        submission = {
            'user_id': session['user_id'],
            'challenge_id': challenge_id,
            'code': code,
            'timestamp': datetime.utcnow(),
            'evaluation': evaluation,
            'status': 'correct' if evaluation.get('is_correct') else 'incorrect'
        }
        db.submissions.insert_one(submission)
        
        # After evaluation, update user progress based on result
        if evaluation.get('is_correct'):
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {
                    '$inc': {
                        'correct_solutions': 1,
                        'current_streak': 1
                    }
                }
            )
        else:
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {
                    '$inc': {'incorrect_solutions': 1},
                    '$set': {'current_streak': 0}
                }
            )
        
        return jsonify({
            'status': 'success',
            **evaluation  # Include all evaluation fields
        })
        
    except Exception as e:
        print(f"Error in submit_solution: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to evaluate solution',
            'details': str(e)
        }), 500

@app.route('/api/user_progress')
def user_progress():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not user:
            return jsonify({
                'challenges_attempted': 0,
                'correct_solutions': 0,
                'incorrect_solutions': 0,
                'current_streak': 0
            })
            
        return jsonify({
            'challenges_attempted': user.get('challenges_attempted', 0),
            'correct_solutions': user.get('correct_solutions', 0),
            'incorrect_solutions': user.get('incorrect_solutions', 0),
            'current_streak': user.get('current_streak', 0)
        })
    except Exception as e:
        print(f"Error fetching user progress: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 