"""
setup_database.py
-----------------
One-time database setup. Run it once after PostgreSQL is running.

What it does:
  1. Connects to PostgreSQL as the administrator (usually "postgres").
  2. Creates two database users, with the passwords from the .env file:
       - the app user        : owns the tables, can read and write
       - the read-only user  : can only SELECT from uploaded dataset tables
  3. Creates the project database.
  4. Creates the "datasets" schema and sets the permissions so the read-only
     user can read dataset tables but can never see the users table.

How to run (from the backend folder, with the virtual environment active):
    python scripts/setup_database.py

It is safe to run more than once.
"""

import getpass
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

# Let this script import the "app" package from the backend folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATASET_SCHEMA, get_settings  # noqa: E402


def connect_as_admin(settings, database):
    """Try the administrator password from .env first. If it is wrong, ask for it."""
    password = settings.postgres_superuser_password
    for attempt in range(3):
        try:
            connection = psycopg2.connect(
                host=settings.db_host, port=settings.db_port, dbname=database,
                user=settings.postgres_superuser, password=password, connect_timeout=8)
            connection.autocommit = True
            settings.postgres_superuser_password = password   # remember the one that worked
            return connection
        except psycopg2.OperationalError as error:
            message = str(error)
            if "password" in message.lower() or "authentication" in message.lower():
                print(f"\nPostgreSQL did not accept the password for user "
                      f"'{settings.postgres_superuser}'.")
                print("Type the password you chose when you installed PostgreSQL.")
                password = getpass.getpass("Password (it stays hidden while you type): ")
                continue
            sys.exit(
                f"\nCould not reach PostgreSQL at {settings.db_host}:{settings.db_port}.\n"
                "Check that PostgreSQL is running and that DB_PORT in .env is correct.\n\n"
                f"Details: {message}")
    sys.exit("\nThe password was wrong three times. Stopping.")


def create_or_update_user(cursor, username, password, can_create_db=False):
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (username,))
    action = "ALTER" if cursor.fetchone() else "CREATE"
    cursor.execute(
        sql.SQL("{action} ROLE {name} WITH LOGIN PASSWORD {password} NOSUPERUSER NOCREATEROLE {createdb}")
        .format(action=sql.SQL(action), name=sql.Identifier(username), password=sql.Literal(password),
                createdb=sql.SQL("CREATEDB" if can_create_db else "NOCREATEDB")))
    print(f"  user '{username}': {'updated' if action == 'ALTER' else 'created'}")


def main():
    settings = get_settings()
    app_user, ro_user, db_name = settings.db_app_user, settings.db_readonly_user, settings.db_name
    print(f"Setting up PostgreSQL at {settings.db_host}:{settings.db_port}")

    # ---- Step 1 and 2: users and database (done from the built-in "postgres" database)
    admin = connect_as_admin(settings, "postgres")
    with admin.cursor() as cur:
        create_or_update_user(cur, app_user, settings.db_app_password)
        create_or_update_user(cur, ro_user, settings.db_readonly_password)

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if cur.fetchone():
            print(f"  database '{db_name}': already exists")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(db_name), sql.Identifier(app_user)))
            print(f"  database '{db_name}': created")
    admin.close()

    # ---- Step 3: schema and permissions (done inside the project database)
    admin = connect_as_admin(settings, db_name)
    with admin.cursor() as cur:
        ident = {"app": sql.Identifier(app_user), "ro": sql.Identifier(ro_user),
                 "db": sql.Identifier(db_name), "schema": sql.Identifier(DATASET_SCHEMA)}
        statements = [
            # The app user owns the database and both schemas.
            "ALTER DATABASE {db} OWNER TO {app}",
            "GRANT ALL ON SCHEMA public TO {app}",
            "CREATE SCHEMA IF NOT EXISTS {schema} AUTHORIZATION {app}",
            # The read-only user starts with nothing at all...
            "REVOKE ALL ON DATABASE {db} FROM PUBLIC",
            "REVOKE ALL ON SCHEMA public FROM PUBLIC",
            "REVOKE ALL ON SCHEMA public FROM {ro}",
            "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ro}",
            # ...and then gets only: connect, and read tables in the datasets schema.
            "GRANT CONNECT ON DATABASE {db} TO {app}, {ro}",
            "GRANT USAGE ON SCHEMA {schema} TO {ro}",
            "GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {ro}",
            # Tables the app user creates later are readable by the read-only user too.
            "ALTER DEFAULT PRIVILEGES FOR ROLE {app} IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ro}",
            # Extra safety nets on the read-only user itself.
            "ALTER ROLE {ro} SET default_transaction_read_only = on",
            "ALTER ROLE {ro} SET search_path = {schema}",
        ]
        for statement in statements:
            cur.execute(sql.SQL(statement).format(**ident))
    admin.close()
    print(f"  schema '{DATASET_SCHEMA}' and permissions: done")
    print("\nDatabase setup finished. You can now start the backend.")


if __name__ == "__main__":
    main()
