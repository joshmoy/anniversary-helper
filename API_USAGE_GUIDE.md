# Anniversary Wish API Usage Guide

This guide explains how to use the Anniversary Wish API to generate personalized, AI-powered anniversary wishes.

## Overview

The Anniversary Wish API allows you to generate personalized anniversary wishes using AI. The API is designed to be accessible to both authenticated and non-authenticated users, with rate limiting applied to protect the service.

## Base URL

```
https://your-domain.com/api
```

## Authentication

- **Non-authenticated users**: Can generate wishes but are subject to rate limiting (3 requests per 3 hours per IP)
- **Authenticated users**: Have unlimited access to wish generation
- **Admin users**: Full access to all endpoints

## Rate Limiting

### For Non-Authenticated Users

- **Limit**: 3 requests per 3 hours per IP address
- **Headers**: `Retry-After` header indicates when you can make another request
- **Status Code**: `429 Too Many Requests` when limit is exceeded

### For Authenticated Users

- **Limit**: Unlimited requests
- **Authentication**: Include `Authorization: Bearer <token>` header

## Endpoints

### 1. Generate Anniversary Wish

**POST** `/api/anniversary-wish`

Generate a personalized anniversary wish.

#### Request Body

```json
{
  "name": "John and Sarah",
  "anniversary_type": "wedding-anniversary",
  "relationship": "friend",
  "tone": "warm",
  "context": "They just moved to a new city and are starting a new chapter"
}
```

#### Parameters

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Name of the person(s) celebrating the anniversary (1-100 characters) |
| `anniversary_type` | enum | Yes | Type of anniversary: `birthday`, `work-anniversary`, `wedding-anniversary`, `promotion`, `retirement`, `friendship`, `relationship`, `milestone`, `custom` |
| `relationship` | string | Yes | Your relationship to them (e.g., "friend", "colleague", "spouse", "mentor") - any descriptive text (1-50 characters) |
| `tone` | enum | No | Tone of the message: `professional`, `friendly`, `warm`, `humorous`, `formal` (default: `warm`) |
| `context` | string | No | Additional context for personalization (max 500 characters) |

#### Response

```json
{
  "generated_wish": "🎉 Happy 5th Wedding Anniversary, John and Sarah! As your friend, I'm so grateful to celebrate this beautiful milestone with you. May God continue to bless your marriage as you begin this new chapter in your new city. - Love is patient, love is kind. It does not envy, it does not boast, it is not proud. (1 Corinthians 13:4)",
  "request_id": "123e4567-e89b-12d3-a456-426614174000",
  "remaining_requests": 2,
  "window_reset_time": "2024-01-15T18:00:00Z"
}
```

#### Response Fields

| Field | Type | Description |
| --- | --- | --- |
| `generated_wish` | string | The AI-generated anniversary wish |
| `request_id` | string | Unique identifier for this request |
| `remaining_requests` | integer | Number of requests remaining in current window |
| `window_reset_time` | datetime | When the rate limit window resets (null for authenticated users) |

### 2. Check Rate Limit Status

**GET** `/api/anniversary-wish/rate-limit-info`

Check your current rate limit status without consuming a request.

#### Response

```json
{
  "ip_address": "192.168.1.100",
  "is_authenticated": false,
  "rate_limit_info": {
    "remaining_requests": 2,
    "window_reset_time": "2024-01-15T18:00:00Z",
    "request_count": 1
  }
}
```

## Example Usage

### JavaScript/Node.js

```javascript
const generateAnniversaryWish = async (wishData) => {
  try {
    const response = await fetch("/api/anniversary-wish", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(wishData),
    });

    if (response.status === 429) {
      const retryAfter = response.headers.get("Retry-After");
      throw new Error(`Rate limit exceeded. Try again in ${retryAfter} seconds.`);
    }

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error("Error generating wish:", error);
    throw error;
  }
};

// Example usage
const wishData = {
  name: "John and Sarah",
  anniversary_type: "wedding-anniversary",
  relationship: "friend",
  tone: "warm",
  context: "They just moved to a new city",
};

generateAnniversaryWish(wishData)
  .then((result) => {
    console.log("Generated wish:", result.generated_wish);
    console.log("Remaining requests:", result.remaining_requests);
  })
  .catch((error) => {
    console.error("Failed to generate wish:", error);
  });
```

### Python

```python
import requests
import json

def generate_anniversary_wish(wish_data):
    try:
        response = requests.post(
            '/api/anniversary-wish',
            headers={'Content-Type': 'application/json'},
            json=wish_data
        )

        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            raise Exception(f"Rate limit exceeded. Try again in {retry_after} seconds.")

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error generating wish: {e}")
        raise

# Example usage
wish_data = {
    "name": "John and Sarah",
    "anniversary_type": "wedding-anniversary",
    "relationship": "friend",
    "tone": "warm",
    "context": "They just moved to a new city"
}

try:
    result = generate_anniversary_wish(wish_data)
    print(f"Generated wish: {result['generated_wish']}")
    print(f"Remaining requests: {result['remaining_requests']}")
except Exception as e:
    print(f"Failed to generate wish: {e}")
```

### cURL

```bash
curl -X POST "https://your-domain.com/api/anniversary-wish" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John and Sarah",
    "anniversary_type": "wedding-anniversary",
    "relationship": "friend",
    "tone": "warm",
    "context": "They just moved to a new city"
  }'
```

## Error Handling

### Rate Limit Exceeded (429)

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

**Headers:**

- `Retry-After`: Number of seconds to wait before retrying

### Validation Error (422)

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Server Error (500)

```json
{
  "detail": "Failed to generate anniversary wish. Please try again later."
}
```

## Best Practices

1. **Check Rate Limits**: Use the rate limit info endpoint to check your status before making requests
2. **Handle Errors Gracefully**: Always handle 429 (rate limit) and 500 (server error) responses
3. **Cache Results**: Store generated wishes to avoid unnecessary API calls
4. **Provide Context**: Include meaningful context to get more personalized wishes
5. **Respect Limits**: Don't attempt to bypass rate limits

## Anniversary Types

- **birthday**: Birthday celebrations
- **work-anniversary**: Work anniversaries (job start date, etc.)
- **wedding-anniversary**: Wedding anniversaries
- **promotion**: Promotion celebrations
- **retirement**: Retirement celebrations
- **friendship**: Friendship anniversaries
- **relationship**: General relationship anniversaries
- **milestone**: Special milestone celebrations
- **custom**: Custom anniversary types

## Tone Options

- **professional**: Professional, respectful tone appropriate for workplace relationships
- **friendly**: Friendly, approachable tone that's warm and personable
- **warm**: Warm, heartfelt tone expressing genuine care and affection (default)
- **humorous**: Light, humorous tone with appropriate jokes or playful language
- **formal**: Formal, dignified tone that's respectful and proper

## Relationship Examples

You can use any relationship description that best describes your connection to the person. Here are some common examples:

### Family Relationships

- "spouse", "husband", "wife", "partner"
- "parent", "mother", "father"
- "child", "son", "daughter"
- "sibling", "brother", "sister"
- "family member", "relative", "cousin", "aunt", "uncle"

### Professional Relationships

- "colleague", "coworker", "teammate"
- "boss", "manager", "supervisor"
- "employee", "staff member"
- "client", "customer"
- "mentor", "teacher", "instructor"

### Personal Relationships

- "friend", "best friend", "close friend", "dear friend"
- "neighbor", "roommate"
- "pastor", "minister", "priest"
- "doctor", "therapist", "counselor"

### Custom Relationships

You can also use any custom description that fits your relationship, such as:

- "gym buddy", "hiking partner", "book club member"
- "volunteer coordinator", "community leader"
- "childhood friend", "college roommate"
- Or any other descriptive term that captures your relationship

## Support

For questions or issues with the API, please contact support@anniversaryhelper.com.
