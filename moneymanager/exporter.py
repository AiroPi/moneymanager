from pathlib import Path

import polars as pl

from .cache import cache


def grafana_transactions_exporter(path: Path):
    df = pl.DataFrame(tr for tr in cache.transactions)
    df = df.with_columns((df["amount"] * 100).cast(int))
    df = df.with_columns((df["fee"] * 100).cast(int))

    new_transactions = pl.DataFrame(
        [
            {
                "id": None,
                "bank_name": bank,
                "account_name": account,
                "amount": value * 100,
                "label": "Initial value",
                "date": None,
                "fee": None,
            }
            for bank, accounts in cache.accounts_settings.initial_values.items()
            for account, value in accounts.items()
        ],
        schema=df.schema,
    )

    earliest_dates = df.group_by("bank_name", "account_name").agg(pl.col("date").min().alias("date"))
    new_transactions = (
        new_transactions.join(earliest_dates, on=["bank_name", "account_name"])
        .with_columns(pl.col("date_right").alias("date"))
        .drop("date_right")
    )

    df = df.extend(new_transactions)
    df = df.sort("date")

    df = df.group_by("bank_name", "account_name").agg(
        pl.col("date"), pl.col("amount"), pl.col("amount").cum_sum().alias("state")
    )

    df = df.explode("date", "state", "amount")
    df = df.with_columns((df["amount"] / 100).round(4), (df["state"] / 100).round(4))

    df.write_json(path)
