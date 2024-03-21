import base64
import email
import os.path
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


@dataclass
class Email:
    date: Optional[datetime] = None
    subject: str = ""
    body: str = ""
    attachments: List = field(default_factory=list)
    attachment_links: List = field(default_factory=list)


def extract_text_plain_parts(part: email.message.Message) -> str:
    """Recursively extract 'text/plain' parts from a MIME message."""
    if part.is_multipart():
        for subpart in part.get_payload():
            yield from extract_text_plain_parts(subpart)
    elif part.get_content_type() == "text/plain":
        yield part.get_payload()


def get_or_refresh_credentials(
    scopes: list, token_file_path: str, credentials_file_path: str
):
    credentials = None

    if os.path.exists(token_file_path):
        credentials = Credentials.from_authorized_user_file(
            token_file_path, scopes
        )

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file_path, scopes
            )
            credentials = flow.run_local_server(port=0)
        with open(token_file_path, "w") as token:
            token.write(credentials.to_json())

    return credentials


def get_threads(service, search_filter):
    threads = (
        service.users()
        .threads()
        .list(userId="me", q=search_filter)
        .execute()
        .get("threads", [])
    )
    return threads


def get_top_message(service, thread_id):
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )
    first_message = thread["messages"][0]
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=first_message["id"], format="raw")
        .execute()
    )
    raw_message = msg["raw"]
    mime_msg = email.message_from_bytes(base64.urlsafe_b64decode(raw_message))
    return mime_msg


def process_list(lst):
    # Remove empty elements before the first non-empty element
    first_non_empty_index = next(
        (i for i, x in enumerate(lst) if x.strip()), None
    )
    if first_non_empty_index is not None:
        lst = lst[first_non_empty_index:]

    # Remove empty elements after the last non-empty element
    last_non_empty_index = next(
        (i for i, x in enumerate(lst[::-1]) if x.strip()), None
    )
    if last_non_empty_index is not None:
        last_non_empty_index = len(lst) - last_non_empty_index
        lst = lst[:last_non_empty_index]

    # Collapse consecutive empty elements to only two empty elements
    collapsed_list = []
    for item in lst:
        if item.strip() or (collapsed_list and collapsed_list[-1].strip()):
            collapsed_list.append(item)
        else:
            if len(collapsed_list) < 2 or collapsed_list[-2].strip():
                collapsed_list.append(item)

    for index, item in enumerate(collapsed_list):
        if not item:
            collapsed_list[index] = "\n"

    return collapsed_list


def parse_email(mime_message: email.message.Message) -> Email:
    subject = mime_message.get("Subject")
    message_date = mime_message.get("Date")
    message_date_object = datetime.strptime(
        message_date, "%a, %d %b %Y %H:%M:%S %z"
    )
    body = []

    # Find the main body of the email
    for part in extract_text_plain_parts(mime_message):
        lines = part.splitlines()
        cleaned_lines = [line.strip() for line in lines]
        collapsed_lines = process_list(cleaned_lines)
        message = "".join(collapsed_lines)
        body.append(message)

    _email = Email(
        date=message_date_object, subject=subject, body="\n".join(body)
    )

    return _email


def main():
    _emails = []
    credentials = get_or_refresh_credentials(
        SCOPES, TOKEN_FILE, CREDENTIALS_FILE
    )
    try:
        service = build("gmail", "v1", credentials=credentials)
        threads = get_threads(service, "from:adonis@openmail.co.za")

        for _thread in threads:
            mime_msg = get_top_message(service, _thread["id"])
            _email = parse_email(mime_msg)
            _emails.append(_email)

    except HttpError as error:
        print(f"An HttpError occurred: {error}")

    except Exception as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
