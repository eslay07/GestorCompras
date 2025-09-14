import smtplib


def test_email_connection(email_address: str, email_password: str) -> bool:
    """Verify credentials against the Telconet SMTP server."""
    try:
        with smtplib.SMTP("smtp.telconet.ec", 587) as server:
            server.starttls()
            server.login(email_address, email_password)
        return True
    except Exception:
        return False
