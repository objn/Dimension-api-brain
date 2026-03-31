"""
Node Embedding Service.
Main service for embedding node content with Job integration.

Handles the complete RAG pipeline:
1. CHUNKING - Split node content into chunks
2. COMPARING - Compare with existing chunks (hash-based)
3. EMBEDDING - Create embeddings for new/changed chunks
4. STORING - Save to database with soft delete for removed chunks
"""
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from datetime import datetime
import time
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.database.models import Nodes, Nodevector
from src.services.job_service import (
    job_service, 
    JobContext, 
    JobStatus,
    JobInterruptedException
)

from src.dto.rag_dto import (
    RAGStage, 
    ChunkData, 
    ChunkDiff,
    ExistingChunk,
    NodeEmbeddingResult,
    EMBEDDING_DIMENSIONS
)
from .chunking import ChunkingService, chunking_service
from .embedding import EmbeddingService, embedding_service

logger = logging.getLogger(__name__)


class NodeEmbeddingService:
    """
    Service for embedding node content with full job tracking.
    
    Usage:
        service = NodeEmbeddingService()
        job_id = await service.embed_node(node_id, user_id, db)
        # Check job status via job_service.get_job_status(job_id)
    """
    
    def __init__(
        self,
        chunker: ChunkingService = None,
        embedder: EmbeddingService = None
    ):
        """
        Initialize service with chunking and embedding services.
        
        Args:
            chunker: ChunkingService instance (uses singleton if not provided)
            embedder: EmbeddingService instance (uses singleton if not provided)
        """
        self.chunker = chunker or chunking_service
        self.embedder = embedder or embedding_service
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    async def embed_node(
        self,
        node_id: UUID,
        user_id: UUID,
        db: Session,
        force_reembed: bool = False,
        job_start_time: Optional[datetime] = None,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """
        Start embedding job for a node's content.
        
        This creates a background job and returns immediately.
        Use job_service.get_job_status(job_id) to track progress.
        
        Args:
            node_id: ID of the node to embed
            user_id: ID of the user requesting
            db: Database session
            force_reembed: If True, re-embed all chunks even if unchanged
            job_start_time: If set, passed to register_job; if None, register_job uses its default schedule.
            
        Returns:
            Job ID for tracking
            
        Raises:
            ValueError: If node not found
        """
        # Verify node exists
        node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        if not node:
            raise ValueError(f"Node {node_id} not found")

        base_metadata: Dict[str, Any] = {
            "job_type": "node_content_embedding",
            "node_id": str(node_id),
            "node_name": node.node_name,
            "force_reembed": force_reembed,
            "stage": RAGStage.INIT.value,
            "progress": 0,
        }
        if metadata_extra:
            # Do not allow overriding core identifiers; merge the rest.
            for k in ("job_type", "node_id", "node_name"):
                metadata_extra.pop(k, None)
            base_metadata.update(metadata_extra)

        reg_kwargs: Dict[str, Any] = dict(
            user_id=user_id,
            job_type="node_content_embedding",
            metadata={
                **base_metadata,
            },
            db=db,
        )
        if job_start_time is not None:
            reg_kwargs["job_start_time"] = job_start_time

        job_id = await job_service.register_job(**reg_kwargs)
        
        logger.info(f"Registered embedding job {job_id} for node {node_id}")
        return job_id
    
    async def run_embedding_task(self, ctx: JobContext) -> 'NodeEmbeddingResult':
        """
        Task function called by JobService via TaskRegistry.
        Reads parameters from ctx.metadata and runs the pipeline.
        
        Args:
            ctx: JobContext with metadata containing node_id, force_reembed
            
        Returns:
            NodeEmbeddingResult
        """
        from uuid import UUID as _UUID
        node_id = _UUID(ctx.metadata["node_id"])
        force_reembed = ctx.metadata.get("force_reembed", False)
        
        return await self._run_embedding_pipeline(
            ctx=ctx,
            node_id=node_id,
            user_id=ctx.user_id,
            force_reembed=force_reembed
        )
    
    async def embed_node_sync(
        self,
        node_id: UUID,
        user_id: UUID,
        db: Session,
        force_reembed: bool = False
    ) -> NodeEmbeddingResult:
        """
        Embed node synchronously (blocking).
        Use for immediate embedding without job tracking.
        
        Args:
            node_id: Node ID
            user_id: User ID
            db: Database session
            force_reembed: Force re-embedding
            
        Returns:
            NodeEmbeddingResult with statistics
        """
        # Create a mock context for progress tracking
        context = JobContext(
            job_id=uuid4(),
            user_id=user_id,
            metadata={}
        )
        
        return await self._run_embedding_pipeline(
            ctx=context,
            node_id=node_id,
            user_id=user_id,
            force_reembed=force_reembed,
            db_session=db
        )
    
    def get_node_chunks(
        self,
        node_id: UUID,
        db: Session,
        include_embeddings: bool = False,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a node.
        
        Args:
            node_id: Node ID
            db: Database session
            include_embeddings: Include embedding vectors in response
            include_deleted: Include soft-deleted chunks
            
        Returns:
            List of chunk dictionaries
        """
        query = db.query(Nodevector).filter(
            Nodevector.node_id == node_id
        )
        
        if not include_deleted:
            query = query.filter(Nodevector.deleted_at.is_(None))
        
        chunks = query.order_by(Nodevector.node_vector_chunk_order).all()
        
        result = []
        for chunk in chunks:
            chunk_data = {
                "chunk_id": str(chunk.node_vector_chunk_id),
                "order": chunk.node_vector_chunk_order,
                "content": chunk.node_content_md_chunk,
                "content_hash": chunk.node_content_md_chunk_hash,
                "chunk_type": "metadata" if chunk.node_vector_chunk_order == 0 else "content",
                "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
                "updated_at": chunk.updated_at.isoformat() if chunk.updated_at else None,
                "deleted_at": chunk.deleted_at.isoformat() if chunk.deleted_at else None
            }
            
            if include_embeddings and chunk.embedding:
                chunk_data["embedding"] = list(chunk.embedding)
            
            result.append(chunk_data)
        
        return result
    
    def get_chunk_by_id(
        self,
        chunk_id: UUID,
        db: Session,
        include_embedding: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific chunk by ID.
        
        Args:
            chunk_id: Chunk ID
            db: Database session
            include_embedding: Include embedding vector
            
        Returns:
            Chunk data or None
        """
        chunk = db.query(Nodevector).filter(
            Nodevector.node_vector_chunk_id == chunk_id,
            Nodevector.deleted_at.is_(None)
        ).first()
        
        if not chunk:
            return None
        
        result = {
            "chunk_id": str(chunk.node_vector_chunk_id),
            "node_id": str(chunk.node_id),
            "order": chunk.node_vector_chunk_order,
            "content": chunk.node_content_md_chunk,
            "content_hash": chunk.node_content_md_chunk_hash,
            "chunk_type": "metadata" if chunk.node_vector_chunk_order == 0 else "content",
            "created_at": chunk.created_at.isoformat() if chunk.created_at else None
        }
        
        if include_embedding and chunk.embedding:
            result["embedding"] = list(chunk.embedding)
        
        return result
    
    # =========================================================================
    # Pipeline Implementation
    # =========================================================================
    
    async def _run_embedding_pipeline(
        self,
        ctx: JobContext,
        node_id: UUID,
        user_id: UUID,
        force_reembed: bool,
        db_session: Session = None
    ) -> NodeEmbeddingResult:
        """
        Run the complete embedding pipeline.
        
        Stages:
        1. CHUNKING - Create chunks from node content
        2. COMPARING - Compare with existing chunks
        3. EMBEDDING - Embed new/changed chunks
        4. STORING - Save to database
        """
        start_time = time.time()
        
        # Get database session
        if db_session:
            db = db_session
            should_close = False
        else:
            from src.database import get_db
            db_gen = get_db()
            db = next(db_gen)
            should_close = True
        
        try:
            # Get node
            node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
            if not node:
                raise ValueError(f"Node {node_id} not found")
            
            # Stage 1: CHUNKING
            self._update_stage(ctx, RAGStage.CHUNKING, 10, "Creating chunks...")
            ctx.check_interrupted()
            
            new_chunks = self.chunker.create_all_chunks(
                node_name=node.node_name,
                node_desc=node.node_desc,
                node_content_md=node.node_content_md
            )
            
            logger.info(f"Created {len(new_chunks)} chunks for node {node_id}")
            
            # Stage 2: COMPARING
            self._update_stage(ctx, RAGStage.COMPARING, 20, "Comparing with existing chunks...")
            ctx.check_interrupted()
            
            diff = self._compare_chunks(
                node_id=node_id,
                new_chunks=new_chunks,
                db=db,
                force_reembed=force_reembed
            )
            
            logger.info(
                f"Chunk diff: {len(diff.to_create)} to create, "
                f"{len(diff.to_delete)} to delete, "
                f"{len(diff.unchanged)} unchanged"
            )
            
            # Stage 3: EMBEDDING
            self._update_stage(ctx, RAGStage.EMBEDDING, 30, "Creating embeddings...")
            
            embeddings = []
            if diff.to_create:
                embeddings = await self._embed_chunks(
                    ctx=ctx,
                    chunks=diff.to_create
                )
            
            # Stage 4: STORING
            self._update_stage(ctx, RAGStage.STORING, 85, "Saving to database...")
            ctx.check_interrupted()
            
            self._store_chunks(
                node_id=node_id,
                user_id=user_id,
                diff=diff,
                chunks=diff.to_create,
                embeddings=embeddings,
                db=db
            )
            
            # Complete
            processing_time = time.time() - start_time
            self._update_stage(ctx, RAGStage.COMPLETED, 100, "Embedding complete")
            
            result = NodeEmbeddingResult(
                node_id=node_id,
                chunks_created=len(diff.to_create),
                chunks_deleted=len(diff.to_delete),
                chunks_unchanged=len(diff.unchanged),
                total_chunks=len(new_chunks),
                processing_time_seconds=round(processing_time, 2)
            )
            
            logger.info(f"Embedding complete for node {node_id}: {result}")
            return result
            
        except JobInterruptedException:
            logger.warning(f"Embedding job interrupted for node {node_id}")
            raise
        except Exception as e:
            logger.error(f"Embedding failed for node {node_id}: {e}")
            raise
        finally:
            if should_close:
                try:
                    next(db_gen)
                except StopIteration:
                    pass
    
    def _compare_chunks(
        self,
        node_id: UUID,
        new_chunks: List[ChunkData],
        db: Session,
        force_reembed: bool
    ) -> ChunkDiff:
        """
        Compare new chunks with existing ones using hash.
        
        Args:
            node_id: Node ID
            new_chunks: List of new chunks
            db: Database session
            force_reembed: Force re-embedding all
            
        Returns:
            ChunkDiff with to_delete, to_create, unchanged lists
        """
        # Get existing chunks
        existing = db.query(Nodevector).filter(
            Nodevector.node_id == node_id,
            Nodevector.deleted_at.is_(None)
        ).all()
        
        if force_reembed:
            # Delete all and recreate
            return ChunkDiff(
                to_delete=[v.node_vector_chunk_id for v in existing],
                to_create=new_chunks,
                unchanged=[]
            )
        
        # Build lookup by hash
        existing_by_hash: Dict[str, ExistingChunk] = {}
        for v in existing:
            existing_by_hash[v.node_content_md_chunk_hash] = ExistingChunk(
                chunk_id=v.node_vector_chunk_id,
                order=v.node_vector_chunk_order,
                content_hash=v.node_content_md_chunk_hash
            )
        
        new_hashes = {c.content_hash for c in new_chunks}
        existing_hashes = set(existing_by_hash.keys())
        
        # Determine what to delete (exists but not in new)
        to_delete = []
        for existing_chunk in existing:
            if existing_chunk.node_content_md_chunk_hash not in new_hashes:
                to_delete.append(existing_chunk.node_vector_chunk_id)
        
        # Determine what to create (new or hash not found)
        to_create = []
        unchanged = []
        
        for new_chunk in new_chunks:
            if new_chunk.content_hash in existing_by_hash:
                # Hash matches - unchanged
                unchanged.append(existing_by_hash[new_chunk.content_hash].chunk_id)
            else:
                # New chunk (hash not found)
                to_create.append(new_chunk)
        
        return ChunkDiff(
            to_delete=to_delete,
            to_create=to_create,
            unchanged=unchanged
        )
    
    async def _embed_chunks(
        self,
        ctx: JobContext,
        chunks: List[ChunkData]
    ) -> List[List[float]]:
        """
        Embed chunks with progress tracking.
        
        Args:
            ctx: Job context for progress updates
            chunks: Chunks to embed
            
        Returns:
            List of embeddings
        """
        if not chunks:
            return []
        
        texts = [c.content for c in chunks]
        total = len(texts)
        
        def on_progress(processed: int, total: int):
            # Progress from 30% to 85%
            progress = 30 + int((processed / total) * 55)
            ctx.update_progress(
                progress / 100.0,
                f"Embedded {processed}/{total} chunks"
            )
            ctx.check_interrupted()
        
        embeddings = self.embedder.embed_batch(
            texts=texts,
            on_progress=on_progress
        )
        
        return embeddings
    
    def _store_chunks(
        self,
        node_id: UUID,
        user_id: UUID,
        diff: ChunkDiff,
        chunks: List[ChunkData],
        embeddings: List[List[float]],
        db: Session
    ) -> None:
        """
        Store chunks in database.
        
        Args:
            node_id: Node ID
            user_id: User ID
            diff: Chunk diff
            chunks: New chunks to create
            embeddings: Embeddings for new chunks
            db: Database session
        """
        now = datetime.utcnow()
        
        # Soft delete removed chunks
        if diff.to_delete:
            db.query(Nodevector).filter(
                Nodevector.node_vector_chunk_id.in_(diff.to_delete)
            ).update(
                {
                    Nodevector.deleted_at: now,
                    Nodevector.updated_at: now,
                    Nodevector.updated_by: user_id
                },
                synchronize_session=False
            )
            logger.info(f"Soft deleted {len(diff.to_delete)} chunks")
        
        # Insert new chunks
        for chunk, embedding in zip(chunks, embeddings):
            vector = Nodevector(
                node_id=node_id,
                node_vector_chunk_id=uuid4(),
                node_vector_chunk_order=chunk.order,
                node_content_md_chunk=chunk.content,
                node_content_md_chunk_hash=chunk.content_hash,
                embedding=embedding,
                created_at=now,
                created_by=user_id,
                updated_at=now,
                updated_by=user_id,
                deleted_at=None
            )
            db.add(vector)
        
        db.commit()
        logger.info(f"Created {len(chunks)} new chunks")
    
    def _update_stage(
        self, 
        ctx: JobContext, 
        stage: RAGStage, 
        progress: int, 
        message: str
    ) -> None:
        """Update job stage and progress."""
        ctx.metadata["stage"] = stage.value
        ctx.metadata["progress"] = progress
        ctx.metadata["message"] = message
        ctx.update_progress(progress / 100.0, message)


# Singleton instance
node_embedding_service = NodeEmbeddingService()
