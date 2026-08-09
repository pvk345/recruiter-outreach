import base64
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

import config

# This app only ever runs on http://localhost, but oauthlib refuses the OAuth 2 token
# exchange over plain HTTP by default (a production-only concern) unless told otherwise.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _make_flow(redirect_uri, state=None, code_verifier=None):
    return Flow.from_client_secrets_file(
        config.GMAIL_CLIENT_SECRET_PATH,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )


def get_authorization_url(redirect_uri):
    flow = _make_flow(redirect_uri)
    auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return auth_url, state, flow.code_verifier


def exchange_code(redirect_uri, authorization_response_url, state, code_verifier):
    flow = _make_flow(redirect_uri, state=state, code_verifier=code_verifier)
    flow.fetch_token(authorization_response=authorization_response_url)
    _save_credentials(flow.credentials)


def _save_credentials(creds):
    with open(config.GMAIL_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())


def _load_credentials():
    if not os.path.isfile(config.GMAIL_TOKEN_PATH):
        return None
    creds = Credentials.from_authorized_user_file(config.GMAIL_TOKEN_PATH, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    return creds


def is_connected():
    creds = _load_credentials()
    return bool(creds and creds.valid)


def send_message(to, subject, body, attachment_path=None):
    """Sends via the connected Gmail account. In TEST_SEND_MODE, redirects to
    TEST_SEND_EMAIL instead of the real recipient (subject/body/attachment unchanged)."""
    creds = _load_credentials()
    if not creds or not creds.valid:
        raise RuntimeError("Gmail is not connected. Visit Setup to connect it.")

    actual_to = to
    if config.TEST_SEND_MODE:
        if not config.TEST_SEND_EMAIL:
            raise RuntimeError("TEST_SEND_MODE is on but TEST_SEND_EMAIL is not set in .env")
        actual_to = config.TEST_SEND_EMAIL

    message = MIMEMultipart()
    message["to"] = actual_to
    message["subject"] = subject
    message.attach(MIMEText(body))

    if attachment_path and os.path.isfile(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(attachment_path))
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service = build("gmail", "v1", credentials=creds)
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent["id"]
