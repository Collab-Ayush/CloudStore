
from getpass import getpass
from werkzeug.security import generate_password_hash
from config import get_db_connection

username = input("Enter admin username: ").strip()
password = getpass("Enter admin password: ")
confirm = getpass("Confirm admin password: ")

if not username or not password:
    print("Username and password cannot be empty.")
    raise SystemExit

if password != confirm:
    print("Passwords do not match.")
    raise SystemExit

if len(password) < 10:
    print("Password must contain at least 10 characters.")
    raise SystemExit

connection = get_db_connection()

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO admin_users (username, password_hash)
            VALUES (%s, %s)
            """,
            (username, generate_password_hash(password))
        )

    connection.commit()
    print("Administrator account created successfully!")

except Exception as e:
    connection.rollback()
    print("Error creating administrator:", e)

finally:
    connection.close()
