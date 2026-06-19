"""Memorycore Controller - Primary interface to CozoDB.

Simplified: Local-first memory substrate.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import cozo


# ENUMS

class MemoryType:
    FACT = "fact"
    DECISION = "decision"
    CORRECTION = "correction"
    PROCEDURE = "procedure"
    SOURCE = "source"
    TASK_RESULT = "task_result"
    PREFERENCE = "preference"

    @classmethod
    def values(cls):
        return [cls.FACT, cls.DECISION, cls.CORRECTION, cls.PROCEDURE,
                cls.SOURCE, cls.TASK_RESULT, cls.PREFERENCE]


class MemoryStatus:
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    STALE = "stale"
    ARCHIVED = "archived"

    @classmethod
    def values(cls):
        return [cls.ACTIVE, cls.SUPERSEDED, cls.STALE, cls.ARCHIVED]


class LinkType:
    RELATED = "related"
    DERIVED = "derived"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    REFERENCES = "references"
    DEPENDS_ON = "depends_on"


# DATA CLASSES

@dataclass
class MemoryRecord:
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    content: str = ""
    evidence: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    created_by: str = ""
    tags: List[str] = field(default_factory=list)
    memory_type: str = MemoryType.FACT
    summary: str = ""
    status: str = MemoryStatus.ACTIVE
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "content": self.content,
            "evidence": self.evidence,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "tags": self.tags,
            "memory_type": self.memory_type,
            "summary": self.summary,
            "status": self.status,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        return cls(
            memory_id=data.get("memory_id", str(uuid.uuid4())),
            project_id=data.get("project_id", ""),
            content=data.get("content", ""),
            evidence=data.get("evidence", []),
            created_at=data.get("created_at", datetime.utcnow().isoformat() + "Z"),
            created_by=data.get("created_by", ""),
            tags=data.get("tags", []),
            memory_type=data.get("memory_type", MemoryType.FACT),
            summary=data.get("summary", ""),
            status=data.get("status", MemoryStatus.ACTIVE),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat() + "Z"),
        )


@dataclass
class ProjectRecord:
    project_id: str
    name: str
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    created_by: str = ""
    is_active: bool = True


class MemoryController:
    def __init__(self, db_path: str, schema_path: str, audit_logger=None):
        self.db_path = db_path
        self.schema_path = schema_path
        self.audit_logger = audit_logger
        self.db = None
        self._init_db()

    def _init_db(self):
        self.db = cozo.CozoDb(self.db_path)
        with open(self.schema_path, 'r') as f:
            schema = f.read()
        self.db.run_script(schema)

    def close(self):
        if self.db:
            self.db.close()
            self.db = None

    def add_memory(self, project_id: str, content: str, created_by: str = "",
                   memory_type: str = MemoryType.FACT, summary: str = "",
                   evidence: List[str] = None, tags: List[str] = None) -> MemoryRecord:
        if evidence is None:
            evidence = []
        if tags is None:
            tags = []
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        memory = MemoryRecord(
            memory_id=memory_id, project_id=project_id, content=content,
            evidence=evidence, created_at=now, created_by=created_by,
            tags=tags, memory_type=memory_type,
            summary=summary or self._generate_summary(content),
            status=MemoryStatus.ACTIVE, updated_at=now
        )
        self.db.run_script(f"""
:insert memories {{
    memory_id: '{memory.memory_id}',
    project_id: '{memory.project_id}',
    content: '{self._escape(memory.content)}',
    evidence: {memory.evidence},
    created_at: '{memory.created_at}',
    created_by: '{memory.created_by}',
    tags: {memory.tags},
    memory_type: '{memory.memory_type}',
    summary: '{self._escape(memory.summary)}',
    status: '{memory.status}',
    updated_at: '{memory.updated_at}'
}}
""")
        if self.audit_logger:
            self.audit_logger.log_memory_write(
                memory_id=memory.memory_id, project_id=project_id,
                action="create", user_id=created_by)
        return memory

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        result = self.db.run_script(f"""
memories[memory_id, project_id, content, evidence, created_at,
         created_by, tags, memory_type, summary, status, updated_at]
where memory_id == '{memory_id}'
""")
        if result and len(result) > 0:
            row = result[0]
            return MemoryRecord.from_dict({
                "memory_id": row[0], "project_id": row[1], "content": row[2],
                "evidence": row[3], "created_at": row[4], "created_by": row[5],
                "tags": row[6], "memory_type": row[7], "summary": row[8],
                "status": row[9], "updated_at": row[10]})
        return None

    def update_memory(self, memory_id: str, **kwargs) -> Optional[MemoryRecord]:
        memory = self.get_memory(memory_id)
        if not memory:
            return None
        for key, value in kwargs.items():
            if hasattr(memory, key):
                setattr(memory, key, value)
        memory.updated_at = datetime.utcnow().isoformat() + "Z"
        updates = []
        for fn in ['content', 'evidence', 'tags', 'memory_type', 'summary', 'status', 'updated_at']:
            v = getattr(memory, fn)
            if isinstance(v, str):
                updates.append(f"{fn}: '{self._escape(v)}'")
            elif isinstance(v, list):
                updates.append(f"{fn}: {v}")
            else:
                updates.append(f"{fn}: '{v}'")
        if updates:
            self.db.run_script(f"""
:update memories
where memory_id == '{memory.memory_id}'
set {', '.join(updates)}
""")
            if self.audit_logger:
                self.audit_logger.log_memory_write(
                    memory_id=memory.memory_id, project_id=memory.project_id,
                    action="update", user_id=kwargs.get('updated_by', 'system'))
        return memory

    def search_memories(self, query: str = "", project_id: str = None,
                        memory_type: str = None, status: str = None,
                        tags: List[str] = None, limit: int = 100) -> List[MemoryRecord]:
        conditions = []
        if project_id:
            conditions.append(f"project_id == '{project_id}'")
        if memory_type:
            conditions.append(f"memory_type == '{memory_type}'")
        if status:
            conditions.append(f"status == '{status}'")
        if tags:
            conditions.append(f"all(t in {tags} for t in tags)")
        where_clause = " and ".join(conditions) if conditions else "true"
        results = self.db.run_script(f"""
:func search() -> [{{ memory_id, project_id, content, evidence,
                   created_at, created_by, tags, memory_type,
                   summary, status, updated_at }}] {{
    search ft_index_memories {{ query: '{query}' }} ->
      memory_id, project_id, content, evidence, created_at,
      created_by, tags, memory_type, summary, status, updated_at
    where {where_clause}
    order by score desc
    limit {limit}
}}
:call search()
""")
        return [MemoryRecord.from_dict({
            "memory_id": row[0], "project_id": row[1], "content": row[2],
            "evidence": row[3], "created_at": row[4], "created_by": row[5],
            "tags": row[6], "memory_type": row[7], "summary": row[8],
            "status": row[9], "updated_at": row[10]}) for row in results]

    def list_by_project(self, project_id: str, status: str = None,
                         memory_type: str = None, limit: int = 100) -> List[MemoryRecord]:
        conditions = [f"project_id == '{project_id}'"]
        if status:
            conditions.append(f"status == '{status}'")
        if memory_type:
            conditions.append(f"memory_type == '{memory_type}'")
        where_clause = " and ".join(conditions)
        results = self.db.run_script(f"""
memories[memory_id, project_id, content, evidence, created_at,
         created_by, tags, memory_type, summary, status, updated_at]
where {where_clause}
order by created_at desc
limit {limit}
""")
        return [MemoryRecord.from_dict({
            "memory_id": row[0], "project_id": row[1], "content": row[2],
            "evidence": row[3], "created_at": row[4], "created_by": row[5],
            "tags": row[6], "memory_type": row[7], "summary": row[8],
            "status": row[9], "updated_at": row[10]}) for row in results]

    def supersede(self, old_memory_id: str, new_memory_id: str,
                  reason: str = "", created_by: str = "system") -> bool:
        old = self.get_memory(old_memory_id)
        new = self.get_memory(new_memory_id)
        if not old or not new:
            return False
        self.update_memory(old_memory_id, status=MemoryStatus.SUPERSEDED)
        chain_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        self.db.run_script(f"""
:insert supersession_chains {{
    chain_id: '{chain_id}',
    old_memory_id: '{old_memory_id}',
    new_memory_id: '{new_memory_id}',
    reason: '{self._escape(reason)}',
    created_at: '{now}',
    created_by: '{created_by}'
}}
""")
        if self.audit_logger:
            self.audit_logger.log_supersede(
                old_memory_id=old_memory_id, new_memory_id=new_memory_id,
                reason=reason, user_id=created_by)
        return True

    def retrieve_context(self, project_id: str, limit: int = 50) -> Dict[str, Any]:
        memories = self.list_by_project(project_id, limit=limit)
        stats = self.db.run_script(f""" :call get_project_stats('{project_id}') """)
        stats_result = stats[0] if stats else {}
        tags_result = self.db.run_script(f""" memories[tags] where project_id == '{project_id}' """)
        all_tags = set()
        for row in tags_result:
            all_tags.update(row[0] if row[0] else [])
        recent = self.list_by_project(project_id, limit=10)
        if self.audit_logger:
            self.audit_logger.log_project_context(project_id=project_id, memory_count=len(memories))
        return {"project_id": project_id, "memories": [m.to_dict() for m in memories],
                "stats": dict(stats_result) if stats_result else {}, "tags": list(all_tags),
                "recent": [m.to_dict() for m in recent]}

    def create_project(self, project_id: str, name: str, description: str = "",
                       created_by: str = "system") -> ProjectRecord:
        now = datetime.utcnow().isoformat() + "Z"
        project = ProjectRecord(project_id=project_id, name=name, description=description,
                                created_at=now, created_by=created_by, is_active=True)
        self.db.run_script(f"""
:insert projects {{
    project_id: '{project.project_id}',
    name: '{self._escape(name)}',
    description: '{self._escape(description)}',
    created_at: '{project.created_at}',
    created_by: '{project.created_by}',
    is_active: {str(project.is_active).lower()}
}}
""")
        if self.audit_logger:
            self.audit_logger.log_project_create(project_id=project_id, user_id=created_by)
        return project

    def get_project(self, project_id: str) -> Optional[ProjectRecord]:
        result = self.db.run_script(f"""
projects[project_id, name, description, created_at, created_by, is_active]
where project_id == '{project_id}'
""")
        if result:
            row = result[0]
            return ProjectRecord(project_id=row[0], name=row[1], description=row[2],
                                  created_at=row[3], created_by=row[4], is_active=row[5])
        return None

    def list_projects(self, created_by: str = None) -> List[ProjectRecord]:
        if created_by:
            results = self.db.run_script(f"""
projects[project_id, name, description, created_at, created_by, is_active]
where created_by == '{created_by}'
order by created_at desc
""")
        else:
            results = self.db.run_script("""
projects[project_id, name, description, created_at, created_by, is_active]
order by created_at desc
""")
        return [ProjectRecord(project_id=row[0], name=row[1], description=row[2],
                              created_at=row[3], created_by=row[4], is_active=row[5]) for row in results]

    def health_check(self) -> Dict[str, Any]:
        try:
            return {"status": "healthy", "memory_count": len(self.list_by_project("", limit=1))}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _escape(self, text: str) -> str:
        if text is None:
            return ""
        return text.replace("'", "''")

    def _generate_summary(self, content: str, max_length: int = 200) -> str:
        if not content:
            return ""
        sentences = [s.strip() for s in content.split('.') if s.strip()]
        if sentences:
            return sentences[0][:max_length]
        return content[:max_length]
