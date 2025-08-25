# Church Anniversary & Birthday Helper

An automated system that reads monthly CSV data to detect birthdays and anniversaries, generates Christian-themed celebration messages using AI, and sends them to a WhatsApp group daily.

## Features

- 📅 **Daily Automated Checks**: Automatically checks for birthdays/anniversaries each day
- 📊 **CSV Data Management**: Easy monthly data uploads via CSV files
- 🤖 **AI-Generated Messages**: Creates personalized Christian messages with Bible verses
- 📱 **WhatsApp Integration**: Sends messages directly to your church WhatsApp group
- ⛪ **Christian-Themed**: All messages are crafted with godly content and biblical references
- 💰 **Cost-Effective**: Designed to run on free/low-cost infrastructure

## Technology Stack

- **Backend**: Python with FastAPI
- **AI/LLM**: Groq (free tier) with Llama models
- **WhatsApp**: Twilio WhatsApp API
- **Database**: Supabase (free PostgreSQL)
- **Deployment**: Railway (free tier)
- **Scheduling**: APScheduler

## Estimated Monthly Costs

- **Minimal Setup**: ~$0.30/month (just WhatsApp messages)
- **Production Setup**: ~$5.50/month (includes reliable hosting)

## CSV Format Expected

The monthly CSV should contain columns:

- `name`: Person's full name
- `type`: "birthday" or "anniversary"
- `date`: Date in MM-DD format (e.g., "03-15")
- `year`: Year of birth/marriage (optional, for age calculation)
- `spouse`: Spouse name (for anniversaries, optional)

## Quick Start

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables (see `.env.example`)
4. Upload your CSV data
5. Run the application: `python main.py`

## Configuration

All configuration is done through environment variables:

- `GROQ_API_KEY`: Your Groq API key (free)
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase anon/public key
- `TWILIO_ACCOUNT_SID`: Twilio account SID
- `TWILIO_AUTH_TOKEN`: Twilio auth token
- `WHATSAPP_FROM`: Your Twilio WhatsApp number
- `WHATSAPP_TO`: Target WhatsApp group number
- `SCHEDULE_TIME`: Daily check time (default: "09:00")

## Deployment

This app is designed to deploy easily on Railway's free tier. See `railway.json` for deployment configuration.

## License

MIT License - Feel free to use for your church or religious organization.
