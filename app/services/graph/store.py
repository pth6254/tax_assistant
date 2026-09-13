"""Fixed, parameterized Cypher only; no generated queries or user documents."""
from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase, Query
import config


@asynccontextmanager
async def connect():
    if not config.NEO4J_PASSWORD:
        raise ValueError('NEO4J_PASSWORD is required')
    async with AsyncGraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        connection_timeout=2, connection_acquisition_timeout=2,
        max_transaction_retry_time=0, max_connection_pool_size=2,
    ) as driver:
        yield driver


async def neighbors(keys: list[str]) -> list[dict]:
    async with connect() as driver:
        records, _, _ = await driver.execute_query(Query('''
            UNWIND $keys AS key
            MATCH (s:TaxArticle {key: key})-[r:CITES]->(t:TaxArticle)
            RETURN s.key AS source_key, t.key AS target_key,
                   s.law_name AS source_law, s.article_no AS source_article,
                   t.law_name AS law_name, t.article_no AS article_no,
                   r.evidence AS evidence, r.reference AS reference
            ORDER BY source_key, target_key, reference LIMIT 24
        ''', timeout=2), keys=keys, database_=config.NEO4J_DATABASE,
            routing_='r')
        return [dict(record) for record in records]


async def save_graph(nodes: list[dict], edges: list[dict]):
    async with connect() as driver:
        await driver.execute_query(
            'CREATE CONSTRAINT tax_article_key IF NOT EXISTS '
            'FOR (n:TaxArticle) REQUIRE n.key IS UNIQUE',
            database_=config.NEO4J_DATABASE)
        # Every source is replaced atomically; reruns remove obsolete outgoing
        # edges for that exact immutable source version, not other graph data.
        async def write(tx):
            result = await tx.run('''
                UNWIND $nodes AS row
                MERGE (n:TaxArticle {key: row.key}) SET n += row
                WITH n OPTIONAL MATCH (n)-[old:CITES]->() DELETE old
            ''', nodes=nodes)
            await result.consume()
            result = await tx.run('''
                UNWIND $edges AS row
                MATCH (s:TaxArticle {key: row.source}), (t:TaxArticle {key: row.target})
                MERGE (s)-[r:CITES {reference: row.reference}]->(t)
                SET r.evidence = row.evidence, r.status = 'resolved'
            ''', edges=edges)
            await result.consume()
        async with driver.session(database=config.NEO4J_DATABASE) as session:
            await session.execute_write(write)
