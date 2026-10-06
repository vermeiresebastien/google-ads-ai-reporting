from gads.platforms import repair_sqlite_ad_account_foreign_keys
from sqlalchemy import create_engine, text


def test_repair_rewrites_foreign_keys_off_ad_accounts_old(tmp_path):
    path = tmp_path / "broken.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("CREATE TABLE ad_accounts (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO ad_accounts (id) VALUES ('acc-1')"))
        connection.execute(
            text(
                """
                CREATE TABLE sync_runs (
                    id VARCHAR(36) PRIMARY KEY,
                    account_id VARCHAR(36) NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES ad_accounts_old (id) ON DELETE CASCADE
                )
                """
            )
        )
        connection.execute(text("INSERT INTO sync_runs (id, account_id) VALUES ('run-1', 'acc-1')"))
        connection.execute(text("PRAGMA foreign_keys=ON"))

    repair_sqlite_ad_account_foreign_keys(engine)

    with engine.connect() as connection:
        fks = list(connection.execute(text("PRAGMA foreign_key_list(sync_runs)")))
        assert fks[0][2] == "ad_accounts"
        assert connection.execute(text("SELECT count(*) FROM sync_runs")).scalar() == 1
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("INSERT INTO sync_runs (id, account_id) VALUES ('run-2', 'acc-1')"))
        connection.commit()
        assert connection.execute(text("SELECT count(*) FROM sync_runs")).scalar() == 2
