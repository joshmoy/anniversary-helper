# Church Anniversary & Birthday Helper

An automated system that reads monthly CSV data to detect birthdays and anniversaries, generates Christian-themed celebration messages using AI, and either sends a personal daily reminder to each user or delivers celebration messages directly to recipient contacts.

## Features

- 📅 **Daily Automated Checks**: Automatically checks for birthdays/anniversaries each day
- 📊 **CSV Data Management**: Easy monthly data uploads via CSV files
- 🤖 **AI-Generated Messages**: Creates personalized Christian messages with Bible verses
- 📱 **Flexible Delivery**: Each user can choose a personal daily reminder or direct delivery to recipient contacts
- ⛪ **Christian-Themed**: All messages are crafted with godly content and biblical references
- 💰 **Cost-Effective**: Designed to run on free/low-cost infrastructure

## Technology Stack

- **Backend**: Python with FastAPI
- **AI/LLM**: Groq (free tier) with Llama models
- **Messaging**: Twilio for SMS/WhatsApp, SMTP for email, Telegram Bot API for Telegram
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
2. Create and activate virtual environment:

   **Option A: Using UV (Recommended - Much Faster)**

   ```bash
   # Install UV if you haven't already
   curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
   # or: pip install uv

   # Create and activate venv with UV
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

   **Option B: Using Standard Python venv**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   **With UV (Faster):**

   ```bash
   uv pip install -r requirements.txt
   ```

   **With pip:**

   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables (see `.env.example`)
5. Upload your CSV data
6. Run the application: `python run.py`

## Configuration

All configuration is done through environment variables:

- `GROQ_API_KEY`: Your Groq API key (free)
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase anon/public key
- `TWILIO_ACCOUNT_SID`: Twilio account SID
- `TWILIO_AUTH_TOKEN`: Twilio auth token
- `SMS_FROM`: Your Twilio SMS-enabled number when using SMS delivery
- `WHATSAPP_FROM`: Your Twilio WhatsApp number when using WhatsApp delivery
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL`: SMTP settings for email delivery
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: Telegram bot settings for Telegram delivery

Users configure their own `phone_number`, `notification_preference`, `notification_channels`, and `direct_message_channel` through the app profile endpoints instead of environment variables.
- `SCHEDULE_TIME`: Daily check time (default: "09:00")

## Auth Hashing without Passlib

This application uses native `bcrypt` for password hashing instead of Passlib. This provides better compatibility and eliminates dependency issues.

### Migration from Passlib

If you're upgrading from a version that used Passlib:

1. **Uninstall Passlib:**

   ```bash
   pip uninstall -y passlib
   ```

2. **Install updated dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run tests to verify:**

   ```bash
   pytest -q
   ```

4. **Local smoke test:**
   - Start the server: `python run.py`
   - Test login endpoint: `POST /auth/login`

### Password Hashing Details

- Uses native `bcrypt==4.1.3` for password hashing
- Existing bcrypt hashes (e.g., `$2b$...`, `$2a$...`, `$2y$...`) continue to work
- No database schema changes required
- Compatible with Python 3.12 on Railway

## Database Migrations

Schema changes are managed with the [Supabase CLI](https://supabase.com/docs/guides/cli).
All migration SQL lives under [`supabase/migrations/`](supabase/migrations/)
and is applied manually via the `make` targets defined in [`Makefile`](Makefile).

```bash
# Against a running local stack (spun up with `make db-start`)
make db-reset

# Against the linked remote Supabase project
export SUPABASE_ACCESS_TOKEN=... SUPABASE_PROJECT_REF=... SUPABASE_DB_PASSWORD=...
make db-migrate
```

Common targets (run `make help` for the full list):

| Command | Purpose |
| ------- | ------- |
| `make db-start` / `db-stop` | Start / stop the local Supabase stack. |
| `make db-reset` | Re-apply every migration against the local stack. |
| `make db-link` | Link the repo to a remote Supabase project (reads `SUPABASE_PROJECT_REF`). |
| `make db-push` | Push migrations to the already-linked remote project. |
| `make db-migrate` | Link (using `SUPABASE_*` env vars) and push in one step. |
| `make db-new NAME=<name>` | Create a new empty migration file. |
| `make db-diff NAME=<name>` | Generate a migration from local schema changes. |
| `make db-list` | List local vs remote migration status. |

See [`supabase/migrations/README.md`](supabase/migrations/README.md) for the
full list of migrations and instructions for adding new ones.

## Deployment

This app is designed to deploy easily on Railway's free tier. See `railway.json` for deployment configuration.

## License

MIT License - Feel free to use for your church or religious organization.
