# Setup Guide for Church Anniversary & Birthday Helper

This guide will walk you through setting up the Church Anniversary & Birthday Helper application.

## Prerequisites

- Python 3.11 or higher
- Git
- A Supabase account (free)
- A Twilio account (for WhatsApp)
- A Groq account (free) or OpenAI account

## Step 1: Clone and Setup

```bash
git clone <your-repo-url>
cd anniversary-helper
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Step 2: Create Supabase Database

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project
3. Go to Settings > API to get your URL and keys
4. Go to SQL Editor and run these commands to create tables:

```sql
-- Create people table
CREATE TABLE IF NOT EXISTS people (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('birthday', 'anniversary')),
    event_date VARCHAR(5) NOT NULL,
    year INTEGER,
    spouse VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create message_logs table
CREATE TABLE IF NOT EXISTS message_logs (
    id SERIAL PRIMARY KEY,
    person_id INTEGER REFERENCES people(id),
    message_content TEXT NOT NULL,
    sent_date DATE NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create csv_uploads table
CREATE TABLE IF NOT EXISTS csv_uploads (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    records_processed INTEGER NOT NULL,
    records_added INTEGER NOT NULL,
    records_updated INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT
);
```

## Step 3: Setup Twilio WhatsApp

1. Create a [Twilio account](https://www.twilio.com)
2. Go to Console > Messaging > Try it out > Send a WhatsApp message
3. Follow the sandbox setup instructions
4. Note your Account SID, Auth Token, and WhatsApp numbers

## Step 4: Get AI API Keys

### Option A: Groq (Recommended - Free)

1. Go to [console.groq.com](https://console.groq.com)
2. Create account and get API key

### Option B: OpenAI (Fallback)

1. Go to [platform.openai.com](https://platform.openai.com)
2. Create account and get API key

## Step 5: Configure Environment

1. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

2. Edit `.env` with your actual values:

```env
# AI/LLM Configuration
GROQ_API_KEY=your_actual_groq_api_key
OPENAI_API_KEY=your_openai_key_if_using

# Supabase Database Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key

# Twilio WhatsApp Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=whatsapp:+your_group_number

# Application Configuration
SCHEDULE_TIME=09:00
TIMEZONE=America/New_York
```

## Step 6: Test Locally

```bash
python app/main.py
```

Visit `http://localhost:8000` to see the API documentation.

## Step 7: Upload Your Data

1. Prepare your CSV file with columns: `name`, `type`, `date`, `year`, `spouse`
2. Use the `/upload-csv` endpoint to upload files directly to Supabase Storage
3. Process it using the API

## Step 8: Deploy to Railway

1. Create a [Railway account](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables in Railway dashboard
4. Deploy!

## Testing

Test the system:

```bash
# Check health
curl http://localhost:8000/health

# Get today's celebrations
curl http://localhost:8000/celebrations/today

# Manual test send
curl -X POST http://localhost:8000/send-celebrations
```

## Troubleshooting

- Check logs for error messages
- Verify all environment variables are set
- Test database connection via `/health` endpoint
- Ensure WhatsApp sandbox is properly configured
