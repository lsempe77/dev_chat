"""
DevChat v2.0 SOTA - Knowledge Graph Service

Entity extraction and graph-based retrieval for impact evaluations.

Graph Schema:
- (Study) - study/document node
- (Author) - researcher
- (Institution) - organization/university
- (Country) - geographic location
- (Sector) - domain (education, health, etc.)
- (Intervention) - program/policy type
- (Outcome) - measured effect

Relationships:
- (Study)-[:AUTHORED_BY]->(Author)
- (Study)-[:AFFILIATED_WITH]->(Institution)
- (Study)-[:CONDUCTED_IN]->(Country)
- (Study)-[:BELONGS_TO]->(Sector)
- (Study)-[:EVALUATES]->(Intervention)
- (Study)-[:MEASURES]->(Outcome)
- (Study)-[:CITES]->(Study)
- (Study)-[:CONTRADICTS]->(Study)
- (Study)-[:SUPPORTS]->(Study)
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.database.neo4j_connection import get_neo4j_connection
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GraphEntity:
    """Extracted entity from document."""
    entity_type: str  # Study, Author, Country, etc.
    name: str
    properties: Dict[str, Any]


@dataclass
class GraphRelation:
    """Relationship between entities."""
    source: str
    relation_type: str  # AUTHORED_BY, CONDUCTED_IN, etc.
    target: str
    properties: Optional[Dict[str, Any]] = None


class EntityExtractor:
    """
    Extract structured entities from document metadata and content.
    
    Uses both metadata parsing and optional LLM extraction.
    """
    
    def __init__(self, llm=None):
        self._llm = llm
    
    def _get_llm(self):
        """Get or create LLM for entity extraction."""
        if self._llm is None:
            from llama_index.llms.openai_like import OpenAILike
            self._llm = OpenAILike(
                model=settings.llm_fast_model,
                api_key=settings.openrouter_api_key,
                api_base=settings.openrouter_base_url,
                temperature=0.0,
                max_tokens=1024,
                is_chat_model=True,
            )
        return self._llm
    
    def extract_from_metadata(self, doc_metadata: Dict[str, Any]) -> tuple[List[GraphEntity], List[GraphRelation]]:
        """
        Extract entities from document metadata.
        
        Args:
            doc_metadata: Document metadata dict
            
        Returns:
            Tuple of (entities, relations)
        """
        entities = []
        relations = []
        
        doc_id = doc_metadata.get("id") or doc_metadata.get("doc_id") or doc_metadata.get("study_id")
        title = doc_metadata.get("title", "Unknown")
        
        if not doc_id:
            logger.warning("Document has no ID, skipping entity extraction")
            return entities, relations
        
        # Create Study node
        study_entity = GraphEntity(
            entity_type="Study",
            name=doc_id,
            properties={
                "title": title,
                "year": doc_metadata.get("year"),
                "abstract": doc_metadata.get("abstract", "")[:500],
                "study_type": doc_metadata.get("study_type"),
                "doi": doc_metadata.get("doi"),
            }
        )
        entities.append(study_entity)
        
        # Extract Authors
        authors = doc_metadata.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",")]
        
        for author in authors[:10]:  # Limit to 10 authors
            if author:
                entities.append(GraphEntity(
                    entity_type="Author",
                    name=author,
                    properties={}
                ))
                relations.append(GraphRelation(
                    source=doc_id,
                    relation_type="AUTHORED_BY",
                    target=author,
                ))
        
        # Extract Countries
        countries = doc_metadata.get("countries", [])
        if isinstance(countries, str):
            countries = [c.strip() for c in countries.split(",")]
        
        for country in countries:
            if country:
                entities.append(GraphEntity(
                    entity_type="Country",
                    name=country,
                    properties={}
                ))
                relations.append(GraphRelation(
                    source=doc_id,
                    relation_type="CONDUCTED_IN",
                    target=country,
                ))
        
        # Extract Sectors
        sectors = doc_metadata.get("sectors", [])
        if isinstance(sectors, str):
            sectors = [s.strip() for s in sectors.split(",")]
        
        for sector in sectors:
            if sector:
                entities.append(GraphEntity(
                    entity_type="Sector",
                    name=sector,
                    properties={}
                ))
                relations.append(GraphRelation(
                    source=doc_id,
                    relation_type="BELONGS_TO",
                    target=sector,
                ))
        
        # Extract Institution
        institution = doc_metadata.get("institution") or doc_metadata.get("publisher")
        if institution:
            entities.append(GraphEntity(
                entity_type="Institution",
                name=institution,
                properties={}
            ))
            relations.append(GraphRelation(
                source=doc_id,
                relation_type="AFFILIATED_WITH",
                target=institution,
            ))
        
        # Extract Intervention
        intervention = doc_metadata.get("intervention_type")
        if intervention:
            entities.append(GraphEntity(
                entity_type="Intervention",
                name=intervention,
                properties={}
            ))
            relations.append(GraphRelation(
                source=doc_id,
                relation_type="EVALUATES",
                target=intervention,
            ))
        
        return entities, relations
    
    async def extract_from_content(self, doc_id: str, content: str) -> tuple[List[GraphEntity], List[GraphRelation]]:
        """
        Extract entities from document content using LLM.
        
        Args:
            doc_id: Document ID
            content: Document text content
            
        Returns:
            Tuple of (entities, relations)
        """
        # Truncate content for LLM
        content = content[:4000]
        
        extraction_prompt = f"""Extract key entities from this impact evaluation document.

Document: {content}

Return JSON with entities and relations:
{{
  "interventions": ["list of interventions/programs evaluated"],
  "outcomes": ["list of outcomes measured"],
  "findings": ["key findings with direction (positive/negative/null)"],
  "countries": ["countries if not obvious"],
  "related_studies": ["studies cited or compared to"]
}}

JSON only, no explanation:"""

        try:
            llm = self._get_llm()
            response = await llm.acomplete(extraction_prompt)
            
            # Parse JSON
            try:
                data = json.loads(response.text.strip())
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    return [], []
            
            entities = []
            relations = []
            
            # Process interventions
            for intervention in data.get("interventions", []):
                entities.append(GraphEntity(
                    entity_type="Intervention",
                    name=intervention,
                    properties={}
                ))
                relations.append(GraphRelation(
                    source=doc_id,
                    relation_type="EVALUATES",
                    target=intervention,
                ))
            
            # Process outcomes
            for outcome in data.get("outcomes", []):
                entities.append(GraphEntity(
                    entity_type="Outcome",
                    name=outcome,
                    properties={}
                ))
                relations.append(GraphRelation(
                    source=doc_id,
                    relation_type="MEASURES",
                    target=outcome,
                ))
            
            return entities, relations
            
        except Exception as e:
            logger.warning(f"LLM entity extraction failed: {e}")
            return [], []


class KnowledgeGraphService:
    """
    Service for knowledge graph operations.
    
    Handles:
    - Entity and relation storage
    - Graph-based queries
    - Relationship discovery
    """
    
    def __init__(self):
        self.extractor = EntityExtractor()
    
    async def index_document(
        self,
        doc_metadata: Dict[str, Any],
        content: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Index a document into the knowledge graph.
        
        Args:
            doc_metadata: Document metadata
            content: Optional document content for deep extraction
            
        Returns:
            Stats on nodes and relations created
        """
        conn = await get_neo4j_connection()
        if not conn:
            return {"nodes_created": 0, "relationships_created": 0}
        
        # Extract entities from metadata
        entities, relations = self.extractor.extract_from_metadata(doc_metadata)
        
        # Optionally extract from content
        if content and settings.graph_llm_extraction_enabled:
            doc_id = doc_metadata.get("id") or doc_metadata.get("doc_id")
            content_entities, content_relations = await self.extractor.extract_from_content(doc_id, content)
            entities.extend(content_entities)
            relations.extend(content_relations)
        
        # Deduplicate entities by (type, name)
        seen_entities = set()
        unique_entities = []
        for e in entities:
            key = (e.entity_type, e.name)
            if key not in seen_entities:
                seen_entities.add(key)
                unique_entities.append(e)
        
        # Create nodes and relationships
        stats = {"nodes_created": 0, "relationships_created": 0}
        
        for entity in unique_entities:
            query = f"""
            MERGE (n:{entity.entity_type} {{name: $name}})
            ON CREATE SET n += $props
            RETURN n
            """
            try:
                result = await conn.execute_write(query, {
                    "name": entity.name,
                    "props": entity.properties,
                })
                stats["nodes_created"] += result.get("nodes_created", 0)
            except Exception as e:
                logger.warning(f"Failed to create node: {e}")
        
        for relation in relations:
            # Get entity types for source and target
            source_type = "Study"  # Source is always the document
            target_type = next(
                (e.entity_type for e in unique_entities if e.name == relation.target),
                "Entity"
            )
            
            query = f"""
            MATCH (s:{source_type} {{name: $source}})
            MATCH (t:{target_type} {{name: $target}})
            MERGE (s)-[r:{relation.relation_type}]->(t)
            RETURN r
            """
            try:
                result = await conn.execute_write(query, {
                    "source": relation.source,
                    "target": relation.target,
                })
                stats["relationships_created"] += result.get("relationships_created", 0)
            except Exception as e:
                logger.warning(f"Failed to create relationship: {e}")
        
        logger.info(f"Indexed document: {stats['nodes_created']} nodes, {stats['relationships_created']} relations")
        return stats
    
    async def search_related_studies(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for related studies using graph traversal.
        
        Args:
            query: Search query (concept, intervention, country, etc.)
            limit: Max results
            
        Returns:
            List of related studies with paths
        """
        conn = await get_neo4j_connection()
        if not conn:
            return []
        
        # Full-text search across node types
        cypher = """
        CALL db.index.fulltext.queryNodes("entitySearch", $query) YIELD node, score
        WITH node, score
        LIMIT 5
        MATCH (s:Study)-[r]-(node)
        RETURN DISTINCT s.name as study_id, s.title as title, s.year as year,
               type(r) as relation, node.name as related_entity, score
        ORDER BY score DESC
        LIMIT $limit
        """
        
        try:
            results = await conn.execute(cypher, {"query": query, "limit": limit})
            return results
        except Exception as e:
            # Fall back to simple MATCH if fulltext index doesn't exist
            logger.debug(f"Fulltext search failed, using fallback: {e}")
            
            fallback_cypher = """
            MATCH (n) WHERE toLower(n.name) CONTAINS toLower($query)
            WITH n LIMIT 5
            MATCH (s:Study)-[r]-(n)
            RETURN DISTINCT s.name as study_id, s.title as title, s.year as year,
                   type(r) as relation, n.name as related_entity
            ORDER BY s.year DESC
            LIMIT $limit
            """
            try:
                return await conn.execute(fallback_cypher, {"query": query, "limit": limit})
            except Exception as e2:
                logger.warning(f"Graph search failed: {e2}")
                return []
    
    async def find_contradicting_studies(
        self,
        study_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Find studies that contradict the given study.
        
        Args:
            study_id: Study identifier
            
        Returns:
            List of contradicting studies
        """
        conn = await get_neo4j_connection()
        if not conn:
            return []
        
        cypher = """
        MATCH (s1:Study {name: $study_id})-[:CONTRADICTS]-(s2:Study)
        RETURN s2.name as study_id, s2.title as title, s2.year as year
        """
        
        try:
            return await conn.execute(cypher, {"study_id": study_id})
        except Exception as e:
            logger.warning(f"Failed to find contradictions: {e}")
            return []
    
    async def find_supporting_studies(
        self,
        study_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Find studies that support the given study.
        
        Args:
            study_id: Study identifier
            
        Returns:
            List of supporting studies
        """
        conn = await get_neo4j_connection()
        if not conn:
            return []
        
        cypher = """
        MATCH (s1:Study {name: $study_id})-[:SUPPORTS]-(s2:Study)
        RETURN s2.name as study_id, s2.title as title, s2.year as year
        """
        
        try:
            return await conn.execute(cypher, {"study_id": study_id})
        except Exception as e:
            logger.warning(f"Failed to find supporting studies: {e}")
            return []
    
    async def get_study_network(
        self,
        study_id: str,
        depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Get the network of entities around a study.
        
        Args:
            study_id: Study identifier
            depth: How many hops to traverse
            
        Returns:
            Graph structure with nodes and edges
        """
        conn = await get_neo4j_connection()
        if not conn:
            return {"nodes": [], "edges": []}
        
        cypher = """
        MATCH path = (s:Study {name: $study_id})-[*1..$depth]-(connected)
        WITH nodes(path) as ns, relationships(path) as rs
        UNWIND ns as n
        WITH DISTINCT n, rs
        RETURN collect(DISTINCT {id: id(n), label: labels(n)[0], name: n.name}) as nodes,
               [r in rs | {source: id(startNode(r)), target: id(endNode(r)), type: type(r)}] as edges
        """
        
        try:
            results = await conn.execute(cypher, {"study_id": study_id, "depth": depth})
            if results:
                return results[0]
            return {"nodes": [], "edges": []}
        except Exception as e:
            logger.warning(f"Failed to get study network: {e}")
            return {"nodes": [], "edges": []}


# Global service instance
_graph_service: Optional[KnowledgeGraphService] = None


def get_knowledge_graph_service() -> KnowledgeGraphService:
    """Get or create the knowledge graph service."""
    global _graph_service
    if _graph_service is None:
        _graph_service = KnowledgeGraphService()
    return _graph_service
