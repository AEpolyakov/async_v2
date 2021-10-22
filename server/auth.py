import os
import hmac


def server_authenticate(connection, secret_key):
    message = os.urandom(32)
    connection.send(message)

    server_hash = hmac.new(secret_key, message)
    digest = server_hash.digest()
    response = connection.recv(len(digest))
    return hmac.compare_digest(server_hash, response)


if __name__ == '__main__':
    pass
