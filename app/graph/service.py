"""Graph service for reading and writing dependency topology to Neo4j."""

from dataclasses import dataclass, field

from neo4j import AsyncDriver


@dataclass
class GraphProject:
    """A project node in the dependency graph."""

    id: str
    workspace_id: str
    tenant_id: str
    name: str
    language: str
    summary: str = ""


@dataclass
class GraphDependency:
    """A package dependency edge from a project."""

    project_id: str
    package_name: str
    ecosystem: str
    version: str
    is_direct: bool = True


@dataclass
class GraphRelationship:
    """An inter-project relationship edge."""

    source_project_id: str
    target_project_id: str
    relationship_type: str  # imports_from, calls_api, shares_db, shares_package
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class BlastRadiusResult:
    """Result of a blast radius query."""

    package_name: str
    ecosystem: str
    affected_projects: list[dict]  # [{project_id, name, distance, impact_type}]
    total_affected: int


class GraphService:
    """Service for reading and writing the dependency graph in Neo4j."""

    def __init__(self, driver: AsyncDriver | None = None):
        self.driver = driver

    async def write_project(self, project: GraphProject) -> None:
        """Create or update a Project node."""
        query = """
        MERGE (p:Project {id: $id})
        SET p.workspace_id = $workspace_id,
            p.tenant_id = $tenant_id,
            p.name = $name,
            p.language = $language,
            p.summary = $summary,
            p.updated_at = datetime()
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                id=project.id,
                workspace_id=project.workspace_id,
                tenant_id=project.tenant_id,
                name=project.name,
                language=project.language,
                summary=project.summary,
            )

    async def write_dependencies(
        self, project_id: str, deps: list[GraphDependency]
    ) -> None:
        """Write DEPENDS_ON edges from a project to packages. Idempotent."""
        query = """
        MATCH (proj:Project {id: $project_id})
        MERGE (pkg:Package {name: $package_name, ecosystem: $ecosystem})
        MERGE (proj)-[r:DEPENDS_ON]->(pkg)
        SET r.version = $version, r.is_direct = $is_direct, r.updated_at = datetime()
        """
        async with self.driver.session() as session:
            for dep in deps:
                await session.run(
                    query,
                    project_id=project_id,
                    package_name=dep.package_name,
                    ecosystem=dep.ecosystem,
                    version=dep.version,
                    is_direct=dep.is_direct,
                )

    async def write_relationship(self, rel: GraphRelationship) -> None:
        """Write an inter-project relationship edge. Creates project nodes if absent."""
        query = """
        MERGE (src:Project {id: $source_project_id})
        MERGE (tgt:Project {id: $target_project_id})
        MERGE (src)-[r:RELATES_TO]->(tgt)
        SET r.type = $relationship_type,
            r.confidence = $confidence,
            r.metadata = $metadata,
            r.updated_at = datetime()
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                source_project_id=rel.source_project_id,
                target_project_id=rel.target_project_id,
                relationship_type=rel.relationship_type,
                confidence=rel.confidence,
                metadata=str(rel.metadata),
            )

    async def get_workspace_graph(self, workspace_id: str) -> dict:
        """Get full graph for a workspace (nodes + edges)."""
        query = """
        MATCH (p:Project {workspace_id: $workspace_id})
        OPTIONAL MATCH (p)-[d:DEPENDS_ON]->(pkg:Package)
        OPTIONAL MATCH (p)-[r:RELATES_TO]->(other:Project {workspace_id: $workspace_id})
        RETURN p, collect(DISTINCT {package: pkg, edge: d}) as deps,
               collect(DISTINCT {target: other, edge: r}) as rels
        """
        async with self.driver.session() as session:
            result = await session.run(query, workspace_id=workspace_id)
            records = await result.data()

        nodes = []
        edges = []
        packages: dict[str, dict] = {}

        for record in records:
            proj = record["p"]
            nodes.append(
                {
                    "id": proj["id"],
                    "name": proj["name"],
                    "language": proj["language"],
                    "type": "project",
                }
            )

            for dep in record["deps"]:
                if dep["package"]:
                    pkg = dep["package"]
                    pkg_id = f"{pkg['ecosystem']}:{pkg['name']}"
                    if pkg_id not in packages:
                        packages[pkg_id] = {
                            "id": pkg_id,
                            "name": pkg["name"],
                            "ecosystem": pkg["ecosystem"],
                            "type": "package",
                        }
                    edge_data = dep["edge"]
                    edges.append(
                        {
                            "source": proj["id"],
                            "target": pkg_id,
                            "type": "depends_on",
                            "version": edge_data.get("version"),
                        }
                    )

            for rel in record["rels"]:
                if rel["target"]:
                    edge_data = rel["edge"]
                    edges.append(
                        {
                            "source": proj["id"],
                            "target": rel["target"]["id"],
                            "type": edge_data.get("type", "relates_to"),
                            "confidence": edge_data.get("confidence"),
                        }
                    )

        nodes.extend(packages.values())
        return {"nodes": nodes, "edges": edges}

    async def query_blast_radius(
        self, workspace_id: str, package_name: str, ecosystem: str
    ) -> BlastRadiusResult:
        """Find all projects affected by a package update, ordered by distance."""
        query = """
        MATCH (pkg:Package {name: $package_name, ecosystem: $ecosystem})
              <-[:DEPENDS_ON]-(directly_affected:Project {workspace_id: $workspace_id})
        OPTIONAL MATCH path = (directly_affected)<-[:RELATES_TO*1..5]-(indirectly_affected:Project {workspace_id: $workspace_id})
        WITH directly_affected, indirectly_affected,
             CASE WHEN indirectly_affected IS NOT NULL THEN length(path) ELSE 0 END as distance
        RETURN directly_affected as project, 1 as distance, 'direct' as impact_type
        UNION
        MATCH (pkg:Package {name: $package_name, ecosystem: $ecosystem})
              <-[:DEPENDS_ON]-(direct:Project {workspace_id: $workspace_id})
              <-[:RELATES_TO*1..5]-(indirect:Project {workspace_id: $workspace_id})
        WITH indirect as project, length(
            shortestPath((direct)<-[:RELATES_TO*]-(indirect))
        ) + 1 as distance, 'indirect' as impact_type
        WHERE project <> direct
        RETURN project, distance, impact_type
        ORDER BY distance
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                workspace_id=workspace_id,
                package_name=package_name,
                ecosystem=ecosystem,
            )
            records = await result.data()

        seen: set[str] = set()
        affected = []
        for record in records:
            proj = record["project"]
            if proj["id"] not in seen:
                seen.add(proj["id"])
                affected.append(
                    {
                        "project_id": proj["id"],
                        "name": proj["name"],
                        "distance": record["distance"],
                        "impact_type": record["impact_type"],
                    }
                )

        return BlastRadiusResult(
            package_name=package_name,
            ecosystem=ecosystem,
            affected_projects=affected,
            total_affected=len(affected),
        )

    async def clear_workspace(self, workspace_id: str) -> None:
        """Delete all nodes/edges for a workspace (for re-analysis)."""
        query = """
        MATCH (p:Project {workspace_id: $workspace_id})
        DETACH DELETE p
        """
        async with self.driver.session() as session:
            await session.run(query, workspace_id=workspace_id)


async def get_graph_service() -> GraphService:
    """Factory for dependency injection."""
    from .connection import get_neo4j_driver

    driver = await get_neo4j_driver()
    return GraphService(driver)
