"""
Markdown-aware Chunking Service.
Splits content while preserving structure and context.
"""
import hashlib
import re
from typing import List, Optional, Tuple

from src.dto.rag_dto import (
    ChunkData, 
    ChunkType, 
    CHUNK_SIZE, 
    CHUNK_OVERLAP,
    MIN_CHUNK_SIZE
)


class ChunkingService:
    """
    Service for chunking markdown content intelligently.
    
    Features:
    - Splits by markdown headers first (preserve document structure)
    - Uses overlap for context continuity
    - Creates metadata chunk from node_name + node_desc
    """
    
    def __init__(
        self, 
        chunk_size: int = CHUNK_SIZE, 
        chunk_overlap: int = CHUNK_OVERLAP,
        min_chunk_size: int = MIN_CHUNK_SIZE
    ):
        """
        Initialize chunking service.
        
        Args:
            chunk_size: Target size for each chunk
            chunk_overlap: Overlap between consecutive chunks
            min_chunk_size: Minimum chunk size (merge if smaller)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def create_all_chunks(
        self,
        node_name: str,
        node_desc: Optional[str],
        node_content_md: Optional[str]
    ) -> List[ChunkData]:
        """
        Create all chunks for a node (metadata + content).
        
        Args:
            node_name: Name of the node
            node_desc: Description of the node
            node_content_md: Markdown content
            
        Returns:
            List of ChunkData, starting with metadata (order=0)
        """
        chunks = []
        
        # Chunk 0: Metadata (node_name + node_desc)
        metadata_chunk = self.create_metadata_chunk(node_name, node_desc)
        chunks.append(metadata_chunk)
        
        # Chunk 1+: Content chunks
        if node_content_md and node_content_md.strip():
            content_chunks = self.create_content_chunks(node_content_md)
            chunks.extend(content_chunks)
        
        return chunks
    
    def create_metadata_chunk(
        self, 
        node_name: str, 
        node_desc: Optional[str]
    ) -> ChunkData:
        """
        Create metadata chunk (order=0) from node_name and node_desc.
        This chunk represents the node's identity for search.
        
        Args:
            node_name: Name of the node
            node_desc: Description of the node
            
        Returns:
            ChunkData for metadata (order=0)
        """
        content_parts = []
        
        if node_name:
            content_parts.append(f"Title: {node_name}")
        
        if node_desc:
            content_parts.append(f"Description: {node_desc}")
        
        content = "\n".join(content_parts) if content_parts else "Untitled Node"
        
        return ChunkData(
            order=0,
            content=content,
            content_hash=self._compute_hash(content),
            chunk_type=ChunkType.METADATA,
            section_header=None,
            start_char=None,
            end_char=None
        )
    
    def create_content_chunks(
        self, 
        content_md: str
    ) -> List[ChunkData]:
        """
        Create content chunks (order=1,2,3...) from markdown content.
        Uses markdown-aware splitting.
        
        Args:
            content_md: Markdown content to chunk
            
        Returns:
            List of ChunkData objects (starting from order=1)
        """
        if not content_md or not content_md.strip():
            return []
        
        # Split by markdown headers first
        sections = self._split_by_headers(content_md)
        
        chunks = []
        current_order = 1
        current_position = 0
        
        for section_header, section_content in sections:
            # Track position in original content
            start_pos = content_md.find(section_content, current_position)
            if start_pos == -1:
                start_pos = current_position
            
            # If section is small enough, keep as one chunk
            if len(section_content) <= self.chunk_size:
                if len(section_content) >= self.min_chunk_size or not chunks:
                    chunks.append(ChunkData(
                        order=current_order,
                        content=section_content,
                        content_hash=self._compute_hash(section_content),
                        chunk_type=ChunkType.CONTENT,
                        section_header=section_header,
                        start_char=start_pos,
                        end_char=start_pos + len(section_content)
                    ))
                    current_order += 1
                elif chunks:
                    # Merge small chunk with previous
                    prev_chunk = chunks[-1]
                    merged_content = prev_chunk.content + "\n\n" + section_content
                    chunks[-1] = ChunkData(
                        order=prev_chunk.order,
                        content=merged_content,
                        content_hash=self._compute_hash(merged_content),
                        chunk_type=ChunkType.CONTENT,
                        section_header=prev_chunk.section_header,
                        start_char=prev_chunk.start_char,
                        end_char=start_pos + len(section_content)
                    )
            else:
                # Split large sections with overlap
                sub_chunks = self._split_with_overlap(
                    section_content, 
                    section_header,
                    start_pos
                )
                for sub_chunk in sub_chunks:
                    sub_chunk.order = current_order
                    chunks.append(sub_chunk)
                    current_order += 1
            
            current_position = start_pos + len(section_content)
        
        return chunks
    
    def _split_by_headers(
        self, 
        content: str
    ) -> List[Tuple[Optional[str], str]]:
        """
        Split content by markdown headers.
        
        Args:
            content: Markdown content
            
        Returns:
            List of (header_line, section_content) tuples
        """
        # Pattern to match markdown headers (# ## ### etc.)
        header_pattern = r'^(#{1,6})\s+(.+)$'
        
        lines = content.split('\n')
        sections = []
        current_header = None
        current_content = []
        
        for line in lines:
            match = re.match(header_pattern, line)
            if match:
                # Save previous section if it has content
                if current_content:
                    section_text = '\n'.join(current_content).strip()
                    if section_text:
                        sections.append((current_header, section_text))
                
                # Start new section
                current_header = line
                current_content = [line]
            else:
                current_content.append(line)
        
        # Don't forget last section
        if current_content:
            section_text = '\n'.join(current_content).strip()
            if section_text:
                sections.append((current_header, section_text))
        
        # If no headers found, return entire content as one section
        if not sections:
            sections = [(None, content.strip())]
        
        return sections
    
    def _split_with_overlap(
        self, 
        content: str, 
        section_header: Optional[str],
        base_position: int = 0
    ) -> List[ChunkData]:
        """
        Split content into chunks with overlap.
        Tries to split at sentence/paragraph boundaries.
        
        Args:
            content: Content to split
            section_header: Header for this section
            base_position: Starting position in original document
            
        Returns:
            List of ChunkData (order will be set later)
        """
        chunks = []
        
        # Split into paragraphs first (double newline)
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_chunk_parts = []
        current_length = 0
        current_start = base_position
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_length = len(para)
            
            # If adding this paragraph exceeds limit and we have content
            if current_length + para_length > self.chunk_size and current_chunk_parts:
                # Create chunk from accumulated content
                chunk_content = '\n\n'.join(current_chunk_parts)
                chunks.append(ChunkData(
                    order=0,  # Will be set later
                    content=chunk_content,
                    content_hash=self._compute_hash(chunk_content),
                    chunk_type=ChunkType.CONTENT,
                    section_header=section_header,
                    start_char=current_start,
                    end_char=current_start + len(chunk_content)
                ))
                
                # Calculate overlap - keep last part of previous chunk
                overlap_parts = []
                overlap_length = 0
                for part in reversed(current_chunk_parts):
                    if overlap_length + len(part) <= self.chunk_overlap:
                        overlap_parts.insert(0, part)
                        overlap_length += len(part)
                    else:
                        break
                
                current_chunk_parts = overlap_parts
                current_length = overlap_length
                current_start = current_start + len(chunk_content) - overlap_length
            
            current_chunk_parts.append(para)
            current_length += para_length
        
        # Don't forget last chunk
        if current_chunk_parts:
            chunk_content = '\n\n'.join(current_chunk_parts)
            if len(chunk_content) >= self.min_chunk_size or not chunks:
                chunks.append(ChunkData(
                    order=0,
                    content=chunk_content,
                    content_hash=self._compute_hash(chunk_content),
                    chunk_type=ChunkType.CONTENT,
                    section_header=section_header,
                    start_char=current_start,
                    end_char=current_start + len(chunk_content)
                ))
            elif chunks:
                # Merge with previous chunk
                prev = chunks[-1]
                merged = prev.content + '\n\n' + chunk_content
                chunks[-1] = ChunkData(
                    order=0,
                    content=merged,
                    content_hash=self._compute_hash(merged),
                    chunk_type=ChunkType.CONTENT,
                    section_header=prev.section_header,
                    start_char=prev.start_char,
                    end_char=current_start + len(chunk_content)
                )
        
        return chunks
    
    def _compute_hash(self, content: str) -> str:
        """
        Compute MD5 hash of content for comparison.
        
        Args:
            content: Text content
            
        Returns:
            MD5 hash as hex string
        """
        # Normalize whitespace before hashing
        normalized = ' '.join(content.split())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()


# Singleton instance
chunking_service = ChunkingService()
