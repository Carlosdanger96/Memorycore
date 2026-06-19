"""Consolidation Engine for Memorycore v2.

Transforms raw task logs (episodes) into durable memory cards.

Raw logs are not memory. They are evidence.
Memorycore needs a consolidator that:
1. Extracts important events from raw logs
2. Identifies reusable facts/procedures
3. Detects conflicts with existing memory
4. Creates memory cards
5. Links cards to evidence
6. Marks stale/superseded memories

This can run:
- After each task (immediate consolidation)
- Nightly (batch consolidation)
- Before major project sessions (pre-session review)
- After user correction (immediate update)
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from server.memory_types import (
    MemoryCard, MemoryType, MemoryStatus, MemoryScope,
    EpisodeRecord, GraphNode, GraphNodeType, GraphEdgeType,
    SupersessionRecord
)
from server.graph_memory import GraphMemory

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEvent:
    """An event extracted from a raw task log."""
    
    event_type: str  # tool_call, file_change, error, warning, decision, etc.
    timestamp: str
    content: str
    raw_text: str
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "content": self.content,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ExtractedFact:
    """A fact extracted from events."""
    
    content: str
    fact_type: str  # semantic, procedural, decision, etc.
    confidence: float = 0.7
    source_events: List[int] = field(default_factory=list)  # Indices of source events
    evidence_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "fact_type": self.fact_type,
            "confidence": self.confidence,
            "source_events": self.source_events,
            "evidence_text": self.evidence_text,
        }


@dataclass
class Conflict:
    """A conflict between extracted information and existing memory."""
    
    conflict_type: str  # contradiction, stale, superseded
    existing_memory_id: str
    new_content: str
    existing_content: str
    severity: float = 0.5  # 0.0 to 1.0
    resolution: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "conflict_type": self.conflict_type,
            "existing_memory_id": self.existing_memory_id,
            "new_content": self.new_content,
            "existing_content": self.existing_content,
            "severity": self.severity,
        }
        if self.resolution:
            result["resolution"] = self.resolution
        return result


@dataclass
class ConsolidationResult:
    """Result of a consolidation operation."""
    
    episode_id: str
    project_id: str
    task_id: str
    events_extracted: int
    facts_extracted: int
    memory_cards_created: int
    memory_cards_updated: int
    conflicts_found: int
    conflicts_resolved: int
    nodes_created: int
    edges_created: int
    processing_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "events_extracted": self.events_extracted,
            "facts_extracted": self.facts_extracted,
            "memory_cards_created": self.memory_cards_created,
            "memory_cards_updated": self.memory_cards_updated,
            "conflicts_found": self.conflicts_found,
            "conflicts_resolved": self.conflicts_resolved,
            "nodes_created": self.nodes_created,
            "edges_created": self.edges_created,
            "processing_time_ms": self.processing_time_ms,
        }


class Consolidator:
    """Consolidates raw episodes into memory cards.
    
    The consolidator transforms raw task logs into structured memory
    that can be efficiently retrieved and used by agents.
    """
    
    def __init__(
        self,
        graph_memory: GraphMemory,
        memory_store: Any = None,
        conflict_threshold: float = 0.85,
        min_confidence: float = 0.6,
    ):
        """Initialize the consolidator.
        
        Args:
            graph_memory: GraphMemory instance for structural relationships
            memory_store: Memory store for persisting memory cards
            conflict_threshold: Similarity threshold for detecting conflicts
            min_confidence: Minimum confidence for creating memory cards
        """
        self.graph = graph_memory
        self.memory_store = memory_store
        self.conflict_threshold = conflict_threshold
        self.min_confidence = min_confidence
        
        # Patterns for extracting events from logs
        self.patterns = {
            "tool_call": re.compile(r'(?i)(tool|function|cmd|command|run|execute)[\s:]+([\w\.]+)'),
            "file_change": re.compile(r'(?i)(write|read|modify|create|delete|update|touch)[\s:]+([\w\/\.\-]+)'),
            "error": re.compile(r'(?i)(error|exception|fail|failed|traceback|stack\s+trace)'),
            "warning": re.compile(r'(?i)(warning|warn|deprecated|caution)'),
            "decision": re.compile(r'(?i)(decide|choose|select|prefer|use|will|should)'),
            "success": re.compile(r'(?i)(success|succeed|complete|done|finished|ok)'),
            "timestamp": re.compile(r'(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})'),
        }
        
        # Keywords for classifying facts
        self.fact_keywords = {
            MemoryType.SEMANTIC: ["fact", "information", "knowledge", "note", "observe", "see"],
            MemoryType.PROCEDURAL: ["how", "to", "step", "procedure", "method", "way", "do", "make"],
            MemoryType.DECISION: ["decide", "choose", "select", "prefer", "use", "will", "should", "because"],
            MemoryType.CORRECTION: ["fix", "correct", "override", "change", "update", "patch", "wrong", "error"],
            MemoryType.SOURCE: ["source", "from", "reference", "cite", "according", "link", "url"],
        }
    
    def consolidate_episode(self, episode: EpisodeRecord) -> ConsolidationResult:
        """Consolidate a single episode into memory cards.
        
        Args:
            episode: EpisodeRecord containing raw task log
            
        Returns:
            ConsolidationResult with statistics
        """
        start_time = datetime.utcnow()
        
        logger.info(f"Consolidating episode: {episode.episode_id} (task: {episode.task_id})")
        
        # Step 1: Extract events from raw log
        events = self._extract_events(episode)
        events_extracted = len(events)
        
        # Step 2: Identify facts and procedures
        facts = self._extract_facts(events)
        facts_extracted = len(facts)
        
        # Step 3: Create memory cards
        memory_cards = []
        for fact in facts:
            if fact.confidence >= self.min_confidence:
                card = self._create_memory_card(fact, episode)
                memory_cards.append(card)
        
        memory_cards_created = len(memory_cards)
        
        # Step 4: Detect conflicts with existing memory
        conflicts = self._detect_conflicts(memory_cards, episode.project_id)
        conflicts_found = len(conflicts)
        
        # Step 5: Resolve conflicts and update existing memory
        memory_cards_updated = 0
        conflicts_resolved = 0
        for conflict in conflicts:
            resolution = self._resolve_conflict(conflict)
            if resolution:
                conflict.resolution = resolution
                conflicts_resolved += 1
                memory_cards_updated += 1
        
        # Step 6: Create graph nodes and edges
        nodes_created, edges_created = self._create_graph_structure(
            episode, events, memory_cards
        )
        
        # Step 7: Persist memory cards
        if self.memory_store:
            for card in memory_cards:
                self.memory_store.create_memory_card(card)
        
        # Step 8: Mark episode as consolidated
        episode.consolidated = True
        
        # Calculate processing time
        end_time = datetime.utcnow()
        processing_time_ms = (end_time - start_time).total_seconds() * 1000
        
        result = ConsolidationResult(
            episode_id=episode.episode_id,
            project_id=episode.project_id,
            task_id=episode.task_id,
            events_extracted=events_extracted,
            facts_extracted=facts_extracted,
            memory_cards_created=memory_cards_created,
            memory_cards_updated=memory_cards_updated,
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            nodes_created=nodes_created,
            edges_created=edges_created,
            processing_time_ms=processing_time_ms,
        )
        
        logger.info(f"Consolidation complete: {result.to_dict()}")
        return result
    
    def consolidate_project(self, project_id: str) -> List[ConsolidationResult]:
        """Consolidate all unconsolidated episodes for a project.
        
        Args:
            project_id: Project ID
            
        Returns:
            List of ConsolidationResult for each episode
        """
        if not self.memory_store:
            logger.warning("No memory store configured, cannot consolidate project")
            return []
        
        # Get all unconsolidated episodes for the project
        episodes = self.memory_store.get_unconsolidated_episodes(project_id)
        
        results = []
        for episode in episodes:
            result = self.consolidate_episode(episode)
            results.append(result)
        
        logger.info(f"Consolidated {len(results)} episodes for project {project_id}")
        return results
    
    def consolidate_all(self) -> Dict[str, List[ConsolidationResult]]:
        """Consolidate all unconsolidated episodes across all projects.
        
        Returns:
            Dictionary mapping project_id to list of ConsolidationResult
        """
        if not self.memory_store:
            logger.warning("No memory store configured, cannot consolidate all")
            return {}
        
        # Get all unconsolidated episodes
        episodes = self.memory_store.get_all_unconsolidated_episodes()
        
        results_by_project: Dict[str, List[ConsolidationResult]] = {}
        for episode in episodes:
            result = self.consolidate_episode(episode)
            if result.project_id not in results_by_project:
                results_by_project[result.project_id] = []
            results_by_project[result.project_id].append(result)
        
        logger.info(f"Consolidated {len(episodes)} episodes across {len(results_by_project)} projects")
        return results_by_project
    
    def _extract_events(self, episode: EpisodeRecord) -> List[ExtractedEvent]:
        """Extract events from raw episode content.
        
        Args:
            episode: EpisodeRecord with raw_content
            
        Returns:
            List of ExtractedEvent
        """
        events = []
        lines = episode.raw_content.split('\n')
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Extract timestamp
            timestamp_match = self.patterns["timestamp"].search(line)
            timestamp = timestamp_match.group(1) if timestamp_match else datetime.utcnow().isoformat()
            
            # Check for each event type
            for event_type, pattern in self.patterns.items():
                if event_type == "timestamp":
                    continue
                
                match = pattern.search(line)
                if match:
                    content = match.group(0)
                    
                    # Extract additional metadata based on event type
                    metadata = {}
                    if event_type == "tool_call" and match.groups():
                        metadata["tool_name"] = match.group(1)
                    elif event_type == "file_change" and match.groups():
                        metadata["file_path"] = match.group(1)
                    
                    event = ExtractedEvent(
                        event_type=event_type,
                        timestamp=timestamp,
                        content=content,
                        raw_text=line,
                        metadata=metadata,
                    )
                    events.append(event)
                    break  # Only one event type per line
        
        logger.debug(f"Extracted {len(events)} events from episode {episode.episode_id}")
        return events
    
    def _extract_facts(self, events: List[ExtractedEvent]) -> List[ExtractedFact]:
        """Extract facts from events.
        
        Args:
            events: List of ExtractedEvent
            
        Returns:
            List of ExtractedFact
        """
        facts = []
        
        # Group events by type
        tool_calls = [e for e in events if e.event_type == "tool_call"]
        file_changes = [e for e in events if e.event_type == "file_change"]
        errors = [e for e in events if e.event_type == "error"]
        warnings = [e for e in events if e.event_type == "warning"]
        decisions = [e for e in events if e.event_type == "decision"]
        successes = [e for e in events if e.event_type == "success"]
        
        # Extract procedural facts from tool calls and file changes
        for event in tool_calls + file_changes:
            # Look for patterns that indicate procedures
            content = event.content.lower()
            
            # Check if this describes a procedure
            if any(keyword in content for keyword in ["how to", "step", "procedure", "method"]):
                fact = ExtractedFact(
                    content=event.content,
                    fact_type=MemoryType.PROCEDURAL,
                    confidence=min(1.0, event.confidence + 0.1),
                    evidence_text=event.raw_text,
                )
                facts.append(fact)
        
        # Extract decision facts
        for event in decisions:
            fact = ExtractedFact(
                content=event.content,
                fact_type=MemoryType.DECISION,
                confidence=event.confidence,
                evidence_text=event.raw_text,
            )
            facts.append(fact)
        
        # Extract correction facts from errors and warnings
        for event in errors + warnings:
            fact = ExtractedFact(
                content=event.content,
                fact_type=MemoryType.CORRECTION,
                confidence=event.confidence,
                evidence_text=event.raw_text,
            )
            facts.append(fact)
        
        # Extract semantic facts from successes and general observations
        for event in successes:
            fact = ExtractedFact(
                content=event.content,
                fact_type=MemoryType.SEMANTIC,
                confidence=event.confidence,
                evidence_text=event.raw_text,
            )
            facts.append(fact)
        
        # Classify facts based on keywords
        for fact in facts:
            if fact.fact_type == MemoryType.SEMANTIC:  # Only classify unclassified facts
                for mem_type, keywords in self.fact_keywords.items():
                    if any(keyword in fact.content.lower() for keyword in keywords):
                        fact.fact_type = mem_type
                        break
        
        logger.debug(f"Extracted {len(facts)} facts from events")
        return facts
    
    def _create_memory_card(self, fact: ExtractedFact, episode: EpisodeRecord) -> MemoryCard:
        """Create a memory card from a fact.
        
        Args:
            fact: ExtractedFact
            episode: Source EpisodeRecord
            
        Returns:
            MemoryCard
        """
        # Determine memory type
        memory_type = fact.fact_type
        
        # Create summary from content (truncate if too long)
        summary = fact.content[:200] if len(fact.content) > 200 else fact.content
        
        # Create memory card
        card = MemoryCard(
            id=f"mc_{uuid.uuid4().hex[:12]}",
            scope=MemoryScope.PROJECT,
            project=episode.project_id,
            type=memory_type,
            summary=summary,
            content=fact.content,
            evidence_ids=[episode.episode_id],
            confidence=fact.confidence,
            status=MemoryStatus.ACTIVE,
            tags=self._extract_tags(fact),
            metadata={
                "source_episode": episode.episode_id,
                "source_task": episode.task_id,
                "source_agent": episode.agent_id,
                "extracted_at": datetime.utcnow().isoformat(),
            }
        )
        
        return card
    
    def _extract_tags(self, fact: ExtractedFact) -> List[str]:
        """Extract tags from a fact.
        
        Args:
            fact: ExtractedFact
            
        Returns:
            List of tags
        """
        tags = []
        
        # Add memory type as tag
        tags.append(fact.fact_type)
        
        # Extract from metadata
        if "tool_name" in fact.metadata:
            tags.append(f"tool:{fact.metadata['tool_name']}")
        if "file_path" in fact.metadata:
            # Extract file extension
            file_path = fact.metadata["file_path"]
            if "." in file_path:
                ext = file_path.split(".")[-1]
                tags.append(f"filetype:{ext}")
        
        # Extract from content
        content_lower = fact.content.lower()
        if "config" in content_lower or "configuration" in content_lower:
            tags.append("config")
        if "database" in content_lower or "db" in content_lower:
            tags.append("database")
        if "api" in content_lower:
            tags.append("api")
        if "error" in content_lower or "fail" in content_lower:
            tags.append("error")
        
        return list(set(tags))  # Deduplicate
    
    def _detect_conflicts(
        self,
        new_cards: List[MemoryCard],
        project_id: str
    ) -> List[Conflict]:
        """Detect conflicts between new memory cards and existing memory.
        
        Args:
            new_cards: List of new MemoryCard to check
            project_id: Project ID for scope
            
        Returns:
            List of Conflict
        """
        conflicts = []
        
        if not self.memory_store:
            return conflicts
        
        # Get existing memory cards for the project
        existing_cards = self.memory_store.get_memory_cards_by_project(project_id)
        
        for new_card in new_cards:
            for existing_card in existing_cards:
                # Skip if same card
                if new_card.id == existing_card.id:
                    continue
                
                # Check for contradictions
                similarity = self._calculate_similarity(new_card.content, existing_card.content)
                
                if similarity > self.conflict_threshold:
                    # High similarity could indicate:
                    # 1. Duplicate information (OK)
                    # 2. Contradictory information (CONFLICT)
                    # 3. Updated information (SUPERSEDES)
                    
                    # Check if content actually contradicts
                    if self._is_contradiction(new_card.content, existing_card.content):
                        conflict = Conflict(
                            conflict_type="contradiction",
                            existing_memory_id=existing_card.id,
                            new_content=new_card.content,
                            existing_content=existing_card.content,
                            severity=similarity,
                        )
                        conflicts.append(conflict)
                    elif self._is_update(new_card.content, existing_card.content):
                        conflict = Conflict(
                            conflict_type="superseded",
                            existing_memory_id=existing_card.id,
                            new_content=new_card.content,
                            existing_content=existing_card.content,
                            severity=similarity,
                        )
                        conflicts.append(conflict)
                    else:
                        # Similar but not contradictory - could be stale
                        conflict = Conflict(
                            conflict_type="stale",
                            existing_memory_id=existing_card.id,
                            new_content=new_card.content,
                            existing_content=existing_card.content,
                            severity=similarity * 0.5,  # Lower severity for stale
                        )
                        conflicts.append(conflict)
        
        logger.debug(f"Detected {len(conflicts)} conflicts")
        return conflicts
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts.
        
        Simple implementation using Jaccard similarity on words.
        For production, use proper semantic similarity (embeddings).
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Tokenize
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _is_contradiction(self, text1: str, text2: str) -> bool:
        """Check if two texts contradict each other.
        
        Simple implementation using negation patterns.
        For production, use more sophisticated NLP.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            True if texts contradict
        """
        # Check for negation patterns
        negations = ["not", "no", "never", "cannot", "should not", "do not", "does not"]
        
        text1_lower = text1.lower()
        text2_lower = text2.lower()
        
        # If one says "use X" and the other says "do not use X"
        for negation in negations:
            if negation in text1_lower and negation not in text2_lower:
                # Check if the non-negated parts are similar
                text1_clean = text1_lower.replace(negation, "")
                text2_clean = text2_lower
                similarity = self._calculate_similarity(text1_clean, text2_clean)
                if similarity > 0.7:
                    return True
            
            if negation in text2_lower and negation not in text1_lower:
                text1_clean = text1_lower
                text2_clean = text2_lower.replace(negation, "")
                similarity = self._calculate_similarity(text1_clean, text2_clean)
                if similarity > 0.7:
                    return True
        
        return False
    
    def _is_update(self, new_text: str, old_text: str) -> bool:
        """Check if new text is an update to old text.
        
        Args:
            new_text: New text
            old_text: Old text
            
        Returns:
            True if new text appears to be an update
        """
        # Check for version numbers, dates, etc.
        version_pattern = re.compile(r'(\d+\.\d+\.\d+|\d+\.\d+)')
        date_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})')
        
        new_versions = version_pattern.findall(new_text)
        old_versions = version_pattern.findall(old_text)
        
        new_dates = date_pattern.findall(new_text)
        old_dates = date_pattern.findall(old_text)
        
        # If new has newer version or date, it's likely an update
        if new_versions and old_versions:
            try:
                new_ver = tuple(map(int, new_versions[0].split('.')))
                old_ver = tuple(map(int, old_versions[0].split('.')))
                if new_ver > old_ver:
                    return True
            except:
                pass
        
        if new_dates and old_dates:
            try:
                new_date = datetime.fromisoformat(new_dates[0])
                old_date = datetime.fromisoformat(old_dates[0])
                if new_date > old_date:
                    return True
            except:
                pass
        
        # Check for update keywords
        update_keywords = ["update", "new", "latest", "current", "now", "recent"]
        old_keywords = ["old", "previous", "former", "outdated"]
        
        new_lower = new_text.lower()
        old_lower = old_text.lower()
        
        if any(kw in new_lower for kw in update_keywords) and \
           any(kw in old_lower for kw in old_keywords):
            return True
        
        return False
    
    def _resolve_conflict(self, conflict: Conflict) -> Optional[str]:
        """Resolve a conflict between memories.
        
        Args:
            conflict: Conflict to resolve
            
        Returns:
            Resolution string, or None if cannot resolve
        """
        if conflict.conflict_type == "contradiction":
            # Mark both as contradicted
            if self.memory_store:
                # Get both memories
                existing = self.memory_store.get_memory_card(conflict.existing_memory_id)
                new_memories = self.memory_store.get_memory_cards_by_content(conflict.new_content)
                
                if existing:
                    existing.status = MemoryStatus.CONTRADICTED
                    self.memory_store.update_memory_card(existing)
                
                for new_mem in new_memories:
                    new_mem.status = MemoryStatus.CONTRADICTED
                    self.memory_store.update_memory_card(new_mem)
            
            return f"Marked {conflict.existing_memory_id} and new memory as contradicted"
        
        elif conflict.conflict_type == "superseded":
            # Mark old as superseded
            if self.memory_store:
                existing = self.memory_store.get_memory_card(conflict.existing_memory_id)
                if existing:
                    existing.status = MemoryStatus.SUPERSEDED
                    existing.stale_after = datetime.utcnow().isoformat()
                    self.memory_store.update_memory_card(existing)
            
            return f"Marked {conflict.existing_memory_id} as superseded"
        
        elif conflict.conflict_type == "stale":
            # Mark old as stale
            if self.memory_store:
                existing = self.memory_store.get_memory_card(conflict.existing_memory_id)
                if existing:
                    existing.status = MemoryStatus.STALE
                    self.memory_store.update_memory_card(existing)
            
            return f"Marked {conflict.existing_memory_id} as stale"
        
        return None
    
    def _create_graph_structure(
        self,
        episode: EpisodeRecord,
        events: List[ExtractedEvent],
        memory_cards: List[MemoryCard]
    ) -> Tuple[int, int]:
        """Create graph structure from episode, events, and memory cards.
        
        Args:
            episode: EpisodeRecord
            events: List of ExtractedEvent
            memory_cards: List of MemoryCard
            
        Returns:
            Tuple of (nodes_created, edges_created)
        """
        nodes_created = 0
        edges_created = 0
        
        # Create task node
        task_node = GraphNode(
            node_id=f"node_{episode.task_id}" if episode.task_id else None,
            node_type=GraphNodeType.TASK,
            name=episode.task_id,
            project_id=episode.project_id,
            properties={
                "agent_id": episode.agent_id,
                "episode_id": episode.episode_id,
                "created_at": episode.created_at,
            }
        )
        task_node = self.graph.add_node(task_node)
        nodes_created += 1
        
        # Create project node if it doesn't exist
        project_node = self.graph._find_node(GraphNodeType.PROJECT, {"name": episode.project_id})
        if not project_node:
            project_node = GraphNode(
                node_type=GraphNodeType.PROJECT,
                name=episode.project_id,
                project_id=episode.project_id,
            )
            project_node = self.graph.add_node(project_node)
            nodes_created += 1
        
        # Link task to project
        edge = GraphEdge(
            from_node_id=task_node.node_id,
            to_node_id=project_node.node_id,
            edge_type=GraphEdgeType.TASK_PART_OF,
            description=f"Task {episode.task_id} is part of project {episode.project_id}",
            created_by=episode.agent_id,
        )
        self.graph.add_edge(edge)
        edges_created += 1
        
        # Create nodes for events
        event_nodes = {}
        for i, event in enumerate(events):
            node_type = self._event_type_to_node_type(event.event_type)
            if node_type:
                node = GraphNode(
                    node_type=node_type,
                    name=f"{event.event_type}_{i}",
                    project_id=episode.project_id,
                    properties={
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "content": event.content,
                        "raw_text": event.raw_text,
                        **event.metadata
                    }
                )
                node = self.graph.add_node(node)
                event_nodes[i] = node
                nodes_created += 1
                
                # Link event to task
                edge = GraphEdge(
                    from_node_id=task_node.node_id,
                    to_node_id=node.node_id,
                    edge_type=self._event_type_to_edge_type(event.event_type),
                    description=f"Task produced {event.event_type}",
                    created_by=episode.agent_id,
                )
                self.graph.add_edge(edge)
                edges_created += 1
        
        # Link memory cards to nodes
        for card in memory_cards:
            # Link to task node
            self.graph.link_memory_to_node(card.id, task_node.node_id)
            
            # Find most relevant event and link to it
            for i, event in enumerate(events):
                if event.content in card.content or card.content in event.content:
                    if i in event_nodes:
                        self.graph.link_memory_to_node(card.id, event_nodes[i].node_id)
                    break
        
        # Create memory card nodes
        for card in memory_cards:
            card_node = GraphNode(
                node_type=GraphNodeType.MEMORY_CARD,
                name=card.id,
                project_id=episode.project_id,
                properties={
                    "memory_id": card.id,
                    "type": card.type,
                    "summary": card.summary,
                }
            )
            card_node = self.graph.add_node(card_node)
            nodes_created += 1
            
            # Link to task
            edge = GraphEdge(
                from_node_id=task_node.node_id,
                to_node_id=card_node.node_id,
                edge_type=GraphEdgeType.MEMORY_DERIVED_FROM,
                description=f"Memory card derived from task",
                created_by=episode.agent_id,
            )
            self.graph.add_edge(edge)
            edges_created += 1
        
        logger.debug(f"Created {nodes_created} nodes and {edges_created} edges")
        return nodes_created, edges_created
    
    def _event_type_to_node_type(self, event_type: str) -> Optional[str]:
        """Map event type to graph node type."""
        mapping = {
            "tool_call": GraphNodeType.TOOL_CALL,
            "file_change": GraphNodeType.FILE,
            "error": GraphNodeType.ERROR,
            "warning": GraphNodeType.ERROR,  # Warnings are a type of error
            "decision": GraphNodeType.DECISION,
            "success": None,  # Don't create node for success
        }
        return mapping.get(event_type)
    
    def _event_type_to_edge_type(self, event_type: str) -> str:
        """Map event type to edge type."""
        mapping = {
            "tool_call": GraphEdgeType.TASK_USED,
            "file_change": GraphEdgeType.TOOL_TOUCHED,
            "error": GraphEdgeType.TASK_PRODUCED,
            "warning": GraphEdgeType.TASK_PRODUCED,
            "decision": GraphEdgeType.TASK_PRODUCED,
        }
        return mapping.get(event_type, GraphEdgeType.TASK_PRODUCED)


def create_consolidator(
    graph_memory: GraphMemory,
    memory_store: Any = None,
    conflict_threshold: float = 0.85,
    min_confidence: float = 0.6,
) -> Consolidator:
    """Factory function to create consolidator.
    
    Args:
        graph_memory: GraphMemory instance
        memory_store: Optional memory store
        conflict_threshold: Similarity threshold for conflicts
        min_confidence: Minimum confidence for memory cards
        
    Returns:
        Consolidator instance
    """
    return Consolidator(
        graph_memory=graph_memory,
        memory_store=memory_store,
        conflict_threshold=conflict_threshold,
        min_confidence=min_confidence,
    )
