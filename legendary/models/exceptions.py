# coding: utf-8

# ToDo more custom exceptions where it makes sense


class CaptchaError(Exception):
    """Raised by core if direct login fails"""
    pass


class InvalidCredentialsError(Exception):
    pass
