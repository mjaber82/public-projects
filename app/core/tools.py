from __future__ import annotations

import json
import random
import re
from datetime import date, datetime
from collections.abc import Mapping, Sequence
from typing import Any

import phonenumbers
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.http.response import HttpResponse
from ipware import get_client_ip
from app.users.models import Country, User

from .constants import ResponseStatus


def create_response(
    status: str = ResponseStatus.FAIL,
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> JsonResponse:
    """Standardized JSON response format for all API endpoints. Status is 'SUCCESS' or 'FAIL'. Payload is optional."""
    response = {"status": status, "message": message}
    if payload is not None:
        response["payload"] = payload
    return JsonResponse(response, json_dumps_params={"default": str})


def json_default_fn(obj: Any) -> str | None:
    """
    default function to handle complex types while dumping to JSON. Below is list of handled types.
    it is used as part of the json.dumps(default=tools.json_default_fn)
        - datetime: if it has isoformat, it calls d.isoformat()
    """

    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def ajax_response(data: Any, allow_cross_domain: bool = False) -> HttpResponse:
    """
    Formats json data as a proper ajax response
    """

    if isinstance(data, HttpResponse):
        response = data
    else:
        response = HttpResponse(
            json.dumps(data, ensure_ascii=False, default=json_default_fn),
            content_type="application/json",
        )
    if allow_cross_domain:
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS, PUT, DELETE"
        response["Access-Control-Max-Age"] = "1000"
        response["Access-Control-Allow-Headers"] = "Origin, X-Titanium-Id, Content-Type, Accept"
    return response


def missing_params(request_bag: Mapping[str, Any], required_list: Sequence[str]) -> list[str]:
    """Checks if required parameters are missing from request data. Returns list of missing params."""
    if not required_list:
        return []
    return [param for param in required_list if not request_bag.get(param)]


def get_ip(request: Any) -> str:
    """Get the IP address of the client. Uses django-ipware to handle various headers and edge cases."""
    ip, is_routable = get_client_ip(request)
    if ip is None:
        return "0.0.0.0"
    return ip


def generate_account_id() -> str:
    """
    Format: XXXXXXXX-XX
    Example: 80789734-04
    """
    return f"{random.randint(10_000_000, 99_999_999)}-{random.randint(0, 99):02d}"


def password_complexity_validator(password: str, min_length: int = 8) -> bool:
    """Checks if password meets complexity requirements."""
    """
        Minimum 8 characters
        At least one uppercase
        At least one lowercase
        At least one digit
        No spaces
    """
    if len(password) < min_length:
        return False
    if re.search(r"\s", password):
        return False
    if not (re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"\d", password)):
        return False
    return True


def validate_username(username: str, min_length: int = 6) -> tuple[str, str | None]:
    """Checks if username length and uniqueness meet requirements. Returns error message if invalid, otherwise None."""
    username = username.strip().lower()
    if len(username) < min_length:
        return username, f"Username must be at least {min_length} characters"
    elif User.objects.filter(username=username).exists():
        return username, "Username already taken"
    return username, None


def validate_dob(dob_str: str, min_age: int | None = None) -> str | None:
    """
    Returns error message if invalid, otherwise None.
    """
    # Parse date
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except ValueError:
        return "Date of birth must be in YYYY-MM-DD format"

    # Age validation only if min_age is provided
    if min_age is not None:
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        if age < min_age:
            return f"You must be at least {min_age} years old"

    return None


def validate_email_address(email: str) -> tuple[str, str | None]:
    """
    Validate email format and uniqueness.
    Returns normalized email (lowercase).
    Returns error message if invalid, otherwise None.
    instance_id: optional, used to skip uniqueness check for an existing user.
    """
    email = email.strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return email, "Invalid email format"

    qs = User.objects.filter(email=email)
    if qs.exists():
        return email, "Email already registered"

    return email, None


def normalize_msisdn(msisdn: str) -> tuple[str | None, Country | None, str | None]:
    """Validate MSISDN format and return normalized number + Country instance."""

    # Parse and validate
    try:
        number = phonenumbers.parse(msisdn, None)
        if not phonenumbers.is_valid_number(number):
            return None, None, "Invalid phone number"
    except phonenumbers.NumberParseException:
        return None, None, "Invalid phone number format"

    # Detect country
    country_code = f"+{number.country_code}"
    try:
        country = Country.objects.get(iso_phone_code=country_code)
    except Country.DoesNotExist:
        return None, None, f"No country found for phone code {country_code}"

    normalized_msisdn = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)

    return normalized_msisdn, country, None


def validate_msisdn(msisdn: str) -> tuple[str | None, Country | None, str | None]:
    """
    Validate MSISDN in E.164 format and enforce uniqueness.
    Returns error message if invalid, otherwise None.
    """
    normalized_msisdn, country, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, None, msisdn_error

    # Check uniqueness (exclude current instance)
    qs = User.objects.filter(msisdn=normalized_msisdn)
    if qs.exists():
        return None, None, "MSISDN already registered"

    return normalized_msisdn, country, None
