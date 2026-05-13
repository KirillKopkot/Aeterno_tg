from enum import IntEnum


class State(IntEnum):
    ENCRYPT_TEXT = 0
    ENCRYPT_KEY = 1
    DECRYPT_TEXT = 2
    DECRYPT_KEY = 3
    ENCRYPT_RESULT = 4
    DECRYPT_RESULT = 5
    UPLOAD_FILE_ENCRYPT = 6
    UPLOAD_FILE_DECRYPT = 7
