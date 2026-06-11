#!/usr/bin/env python
"""Connectivity probe for the Neo4j instance the app would ACTUALLY use.

Resolves credentials exactly like the application (app.config.Config,
which loads .env), attempts a real connection and a real query.
Exit 0 = connected. Loud failure otherwise.

Usage:
    make neo4j-check                         # local (.env values)
    NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io \
    NEO4J_PASSWORD=... make neo4j-check      # probe an Aura instance
"""

import sys

from neo4j import GraphDatabase

from app.config import Config


def main() -> None:
    print(f"target : {Config.NEO4J_URI}")
    print(f"user   : {Config.NEO4J_USER}")
    try:
        with GraphDatabase.driver(
            Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        ) as driver:
            driver.verify_connectivity()
            ok = driver.execute_query("RETURN 1 AS ok").records[0]["ok"]
            assert ok == 1
    except Exception as e:
        print(f"FAIL   : {type(e).__name__}: {e}")
        sys.exit(1)
    print("OK     : connected and answering queries")


if __name__ == "__main__":
    main()
