# API Authentication

The API supports both Django session authentication and JWT authentication.

Session authentication keeps the browsable API working during development when you log in through the normal Django login page.

JWT authentication is for mobile apps and external clients.

## Get Tokens

Send a POST request:

```http
POST http://127.0.0.1:8002/api/token/
Content-Type: application/json
```

Body:

```json
{
  "username": "admin",
  "password": "admin123"
}
```

The response contains:

```json
{
  "refresh": "refresh-token-here",
  "access": "access-token-here"
}
```

## Call Protected API Endpoints

Add this header in Postman or Thunder Client:

```http
Authorization: Bearer access-token-here
```

Example:

```http
GET http://127.0.0.1:8002/api/dashboard/
Authorization: Bearer access-token-here
```

## Refresh Access Token

Send a POST request:

```http
POST http://127.0.0.1:8002/api/token/refresh/
Content-Type: application/json
```

Body:

```json
{
  "refresh": "refresh-token-here"
}
```

The response contains a new access token.

## Notes

- Use the demo credentials printed by `python manage.py seed_demo_data`.
- JWT access tokens last 30 minutes in development.
- JWT refresh tokens last 7 days in development.
- Browser pages such as `/accounts/login/` still use Django sessions.
- The browsable API still works when you are logged in through the browser.
