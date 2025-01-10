# CodeBuddy - Interactive Coding Learning Platform

CodeBuddy is an interactive web application that helps users learn coding through AI-powered challenges and real-time feedback using the Gemini 1.5 Flash API.

## Features

- Real-time chat interface with Gemini 1.5 Flash AI
- Interactive code editor with syntax highlighting
- User authentication and progress tracking
- Challenge-based learning system
- Immediate feedback on solutions
- Progress tracking and analytics

## Technical Stack

- Frontend: HTML, CSS, JavaScript (vanilla)
- Backend: Python Flask
- Database: MongoDB
- AI: Gemini 1.5 Flash API

## Setup Instructions

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables in `.env`:
   ```
   MONGODB_URI=your_mongodb_uri
   GEMINI_API_KEY=your_gemini_api_key
   SECRET_KEY=your_secret_key
   ```
4. Run the application:
   ```bash
   python app.py
   ```

## Environment Variables

- `MONGODB_URI`: MongoDB connection string
- `GEMINI_API_KEY`: Gemini API key
- `SECRET_KEY`: Flask secret key for session management

## Security

- Password hashing using bcrypt
- CSRF protection
- XSS protection
- Rate limiting
- Secure session handling

## Project Structure

```
codebuddy/
├── app.py                 # Main Flask application
├── config.py             # Configuration settings
├── requirements.txt      # Python dependencies
├── static/              # Static files (CSS, JS, images)
├── templates/           # HTML templates
└── models/             # Database models
``` 