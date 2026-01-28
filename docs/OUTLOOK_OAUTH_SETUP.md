# Outlook OAuth Setup Guide

This guide explains how to set up Outlook/Microsoft OAuth authentication for the email service.

## Prerequisites

- A Microsoft account (personal Outlook.com) or Azure AD account (work/school)
- Access to [Azure Portal](https://portal.azure.com)

## Step-by-Step Setup

### 1. Create Azure App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** (or **Microsoft Entra ID**)
3. Click **App registrations** in the left sidebar
4. Click **+ New registration**

### 2. Configure App Registration

**Name**: Give your app a name (e.g., "Mental Health AI Assistant")

**Supported account types**: Choose one:
- **Accounts in any organizational directory and personal Microsoft accounts** (Recommended for personal use)
- **Accounts in any organizational directory** (Work/school only)
- **Personal Microsoft accounts only** (Outlook.com only)

**Redirect URI**: 
- Platform: **Web**
- URI: Your callback URL (e.g., `http://localhost:10000/outlook/oauth2callback` for local dev)
- For production: `https://yourdomain.com/outlook/oauth2callback`

Click **Register**

### 3. Note Your Application (Client) ID

After registration, you'll see the **Overview** page. Copy the **Application (client) ID** - this is your `MICROSOFT_CLIENT_ID`.

### 4. Create Client Secret

1. Go to **Certificates & secrets** in the left sidebar
2. Click **+ New client secret**
3. Add a description (e.g., "Email Service Secret")
4. Choose expiration (24 months recommended)
5. Click **Add**
6. **IMPORTANT**: Copy the **Value** immediately - you won't be able to see it again!
   - This is your `MICROSOFT_CLIENT_SECRET`

### 5. Configure API Permissions

1. Go to **API permissions** in the left sidebar
2. Click **+ Add a permission**
3. Select **Microsoft Graph**
4. Select **Delegated permissions**
5. Add the following permissions:
   - `Mail.ReadWrite` - Read and write mail
   - `Mail.Send` - Send mail
   - `Calendars.ReadWrite` - Read and write calendars (if using calendar features)
   - `Calendars.ReadWrite.Shared` - Read and write shared calendars
   - `User.Read` - Read user profile
   - `offline_access` - Refresh tokens (required for token refresh)

6. Click **Add permissions**
7. **Important**: Click **Grant admin consent** if you're using work/school accounts
   - For personal accounts, users will consent during OAuth flow

### 6. Configure Redirect URIs

1. Go to **Authentication** in the left sidebar
2. Under **Platform configurations**, click **+ Add a platform**
3. Select **Web**
4. Add your redirect URIs:
   - Development: `http://localhost:10000/outlook/oauth2callback`
   - Production: `https://yourdomain.com/outlook/oauth2callback`
   - If using Expo: Add your Expo redirect URL too

5. Under **Implicit grant and hybrid flows**, check:
   - ✅ **Access tokens** (optional, but recommended)
   - ✅ **ID tokens** (optional)

6. Click **Configure**

### 7. Set Environment Variables

Add these to your `.env` file:

```bash
# Microsoft/Outlook OAuth
MICROSOFT_CLIENT_ID=your-application-client-id-here
MICROSOFT_CLIENT_SECRET=your-client-secret-value-here
MICROSOFT_TENANT_ID=common  # Use "common" for personal accounts, or your tenant ID for work/school
```

**Tenant ID Options**:
- `common` - Personal Microsoft accounts (Outlook.com) and work/school accounts
- `organizations` - Work/school accounts only
- `consumers` - Personal Microsoft accounts only
- `{tenant-id}` - Specific organization only

### 8. Test the Setup

1. Start your server
2. Navigate to: `http://localhost:10000/outlook/auth/your-user-id`
3. You should be redirected to Microsoft login
4. After authentication, you'll be redirected back with tokens stored

## Troubleshooting

### Common Issues

**"AADSTS50011: The redirect URI specified in the request does not match"**
- Make sure the redirect URI in Azure Portal exactly matches your callback URL
- Check for trailing slashes, http vs https, etc.

**"AADSTS70011: The provided value for scope is not valid"**
- Verify all scopes are added in API permissions
- Check that scopes match what's in `app/config.py`

**"Invalid client secret"**
- Client secret might have expired
- Create a new secret and update `MICROSOFT_CLIENT_SECRET`

**Token refresh not working**
- Ensure `offline_access` scope is included
- Check that refresh token is being saved in database

### Verification Checklist

- ✅ Application registered in Azure Portal
- ✅ Client ID copied
- ✅ Client secret created and copied
- ✅ API permissions added (Mail.ReadWrite, Mail.Send, User.Read, offline_access)
- ✅ Redirect URIs configured
- ✅ Environment variables set in `.env`
- ✅ Server restarted after adding env vars

## Security Notes

1. **Never commit secrets to git** - Use `.env` file and add to `.gitignore`
2. **Rotate secrets regularly** - Set expiration and rotate before expiry
3. **Use different apps for dev/prod** - Create separate app registrations
4. **Limit redirect URIs** - Only add URIs you actually use
5. **Monitor usage** - Check Azure Portal for suspicious activity

## Additional Resources

- [Microsoft Identity Platform Documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/)
- [Microsoft Graph API Reference](https://docs.microsoft.com/en-us/graph/overview)
- [OAuth 2.0 Flow for Microsoft](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)



