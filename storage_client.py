import hashlib
import json
import math
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple, Callable, Any, Union
from dataclasses import dataclass
from enum import Enum
import base64
import time
import random

# Constants
MAXIMUM_CONCURRENT_UPLOADS = 10
MAX_RETRIES = 3
BASE_DELAY_MS = 1000
MAX_DELAY_MS = 30000

GATEWAY_VERSION = "v1"

HASH_ALGORITHM = "sha256"
SHA256_PREFIX = "sha256:"
DOMAIN_SEPARATOR_FOR_CHUNKS = b"icfs-chunk/"
DOMAIN_SEPARATOR_FOR_METADATA = b"icfs-metadata/"
DOMAIN_SEPARATOR_FOR_NODES = b"ynode/"


class StorageError(Exception):
    """Base exception for storage operations"""
    pass


class HashValidationError(StorageError):
    """Exception raised for hash validation errors"""
    pass


class UploadError(StorageError):
    """Exception raised for upload errors"""
    pass


def validate_hash_format(hash_str: str, context: str) -> None:
    """
    Validate that a hash string has the correct format.
    
    Args:
        hash_str: The hash string to validate
        context: Context description for error messages
        
    Raises:
        HashValidationError: If the hash format is invalid
    """
    if not hash_str:
        raise HashValidationError(f"{context}: Hash cannot be empty")
    
    if not hash_str.startswith(SHA256_PREFIX):
        raise HashValidationError(
            f"{context}: Invalid hash format. Expected format: {SHA256_PREFIX}<64-char-hex>, got: {hash_str}"
        )
    
    hex_part = hash_str[len(SHA256_PREFIX):]  # Remove 'sha256:' prefix
    if len(hex_part) != 64:
        raise HashValidationError(
            f"{context}: Invalid hash format. Expected 64 hex characters after {SHA256_PREFIX}, "
            f"got {len(hex_part)} characters: {hash_str}"
        )
    
    try:
        int(hex_part, 16)
    except ValueError:
        raise HashValidationError(
            f"{context}: Invalid hash format. Hash must contain only hex characters (0-9, a-f), got: {hash_str}"
        )


def is_retriable_error(error: Exception) -> bool:
    """
    Determine if an error should be retried.
    
    Args:
        error: The exception to check
        
    Returns:
        True if the error is retriable, False otherwise
    """
    error_str = str(error).lower()
    
    # Check if it's an aiohttp client error with status code
    if hasattr(error, 'status'):
        status = getattr(error, 'status')
        # Retry on 408 (Request Timeout), 429 (Too Many Requests), and 5xx errors
        if status in (408, 429):
            return True
        if 500 <= status < 600:
            return True
        # Don't retry other 4xx errors
        if 400 <= status < 500:
            return False
    
    # Retry network/connection errors
    network_errors = [
        "ssl", "tls", "network", "connection", "timeout", 
        "reset", "refused", "unreachable", "eof"
    ]
    for term in network_errors:
        if term in error_str:
            return True
    
    # Don't retry validation/logic errors
    non_retriable = [
        "validation", "invalid", "malformed", "unauthorized", 
        "forbidden", "not found", "bad request"
    ]
    for term in non_retriable:
        if term in error_str:
            return False
    
    # Default to retry for unknown errors (conservative approach)
    return True


async def with_retry(operation):
    """
    Execute an operation with exponential backoff retry logic.
    
    Args:
        operation: Async callable to execute
        
    Returns:
        Result of the operation
        
    Raises:
        The last error encountered if all retries fail
    """
    last_error = None
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await operation()
        except Exception as error:
            last_error = error
            
            # Check if this error should be retried
            should_retry = is_retriable_error(error)
            
            # On the final attempt or non-retriable error, raise the error
            if attempt == MAX_RETRIES or not should_retry:
                if not should_retry and attempt < MAX_RETRIES:
                    print(f"Non-retriable error encountered: {error}. Not retrying.")
                raise
            
            # Calculate delay with exponential backoff and jitter
            delay = min(
                BASE_DELAY_MS * (2 ** attempt) + random.random() * 1000,
                MAX_DELAY_MS
            ) / 1000  # Convert to seconds
            
            print(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES + 1}): {error}. "
                  f"Retrying in {delay:.0f}ms...")
            
            await asyncio.sleep(delay)
    
    # This should never happen due to the loop logic
    raise last_error or StorageError("Unknown error occurred during retry attempts")


class YHash:
    """
    Represents a hash used in the storage system.
    """
    
    def __init__(self, bytes_data: bytes):
        """
        Initialize a YHash with raw bytes.
        
        Args:
            bytes_data: 32-byte hash value
            
        Raises:
            ValueError: If bytes_data is not exactly 32 bytes
        """
        if len(bytes_data) != 32:
            raise ValueError(f"YHash must be exactly 32 bytes, got {len(bytes_data)}")
        self.bytes = bytes_data
    
    @classmethod
    async def from_nodes(cls, left: Optional['YHash'], right: Optional['YHash']) -> 'YHash':
        """
        Create a hash from left and right child nodes.
        
        Args:
            left: Left child hash
            right: Right child hash
            
        Returns:
            Combined hash
        """
        left_bytes = left.bytes if left else b"UNBALANCED"
        right_bytes = right.bytes if right else b"UNBALANCED"
        
        combined = DOMAIN_SEPARATOR_FOR_NODES + left_bytes + right_bytes
        hash_bytes = hashlib.sha256(combined).digest()
        return cls(hash_bytes)
    
    @classmethod
    async def from_chunk(cls, data: bytes) -> 'YHash':
        """
        Create a hash from chunk data.
        
        Args:
            data: Chunk data bytes
            
        Returns:
            Chunk hash
        """
        return await cls.from_bytes(DOMAIN_SEPARATOR_FOR_CHUNKS, data)
    
    @classmethod
    async def from_headers(cls, headers: Dict[str, str]) -> 'YHash':
        """
        Create a hash from HTTP headers.
        
        Args:
            headers: Dictionary of headers
            
        Returns:
            Headers hash
        """
        # For each key,value, generate the header line "key: value\n" 
        # where the key and value are trimmed.
        header_lines = []
        for key, value in headers.items():
            header_lines.append(f"{key.strip()}: {value.strip()}\n")
        
        # Sort the header lines alphabetically
        header_lines.sort()
        
        # Hash the header lines with the metadata domain separator
        return await cls.from_bytes(
            DOMAIN_SEPARATOR_FOR_METADATA,
            ''.join(header_lines).encode('utf-8')
        )
    
    @classmethod
    async def from_bytes(cls, domain_separator: bytes, data: bytes) -> 'YHash':
        """
        Create a hash from bytes with a domain separator.
        
        Args:
            domain_separator: Domain separator bytes
            data: Data bytes to hash
            
        Returns:
            Combined hash
        """
        combined = domain_separator + data
        hash_bytes = hashlib.sha256(combined).digest()
        return cls(hash_bytes)
    
    @classmethod
    def from_hex(cls, hex_string: str) -> 'YHash':
        """
        Create a hash from a hex string.
        
        Args:
            hex_string: 64-character hex string
            
        Returns:
            YHash instance
        """
        bytes_data = bytes.fromhex(hex_string)
        return cls(bytes_data)
    
    def to_sha_string(self) -> str:
        """
        Convert to string format with sha256: prefix.
        
        Returns:
            Formatted hash string
        """
        return f"{SHA256_PREFIX}{self.to_hex()}"
    
    def to_hex(self) -> str:
        """
        Convert to hex string.
        
        Returns:
            64-character hex string
        """
        return self.bytes.hex()
    
    def __repr__(self) -> str:
        return f"YHash({self.to_sha_string()})"


@dataclass
class TreeNode:
    """Node in a hash tree"""
    hash: YHash
    left: Optional['TreeNode'] = None
    right: Optional['TreeNode'] = None


@dataclass
class TreeNodeJSON:
    """JSON representation of a tree node"""
    hash: str
    left: Optional['TreeNodeJSON'] = None
    right: Optional['TreeNodeJSON'] = None


def node_to_json(node: TreeNode) -> TreeNodeJSON:
    """Convert a TreeNode to JSON representation"""
    return TreeNodeJSON(
        hash=node.hash.to_sha_string(),
        left=node_to_json(node.left) if node.left else None,
        right=node_to_json(node.right) if node.right else None
    )


@dataclass
class BlobHashTreeJSON:
    """JSON representation of a blob hash tree"""
    tree_type: str
    chunk_hashes: List[str]
    tree: TreeNodeJSON
    headers: List[str]


class BlobHashTree:
    """
    Merkle tree representing a blob's chunks and headers.
    """
    
    def __init__(
        self, 
        chunk_hashes: List[YHash], 
        tree: TreeNode, 
        headers: Optional[Union[List[str], Dict[str, str]]] = None
    ):
        """
        Initialize a blob hash tree.
        
        Args:
            chunk_hashes: List of chunk hashes
            tree: Root node of the tree
            headers: Headers (either list of strings or dictionary)
        """
        self.tree_type = "DSBMTWH"
        self.chunk_hashes = chunk_hashes
        self.tree = tree
        
        if headers is None:
            self.headers = []
        elif isinstance(headers, list):
            self.headers = headers
        else:
            self.headers = [
                f"{key.strip()}: {value.strip()}" 
                for key, value in headers.items()
            ]
        self.headers.sort()
    
    @classmethod
    async def build(
        cls, 
        chunk_hashes: List[YHash], 
        headers: Optional[Dict[str, str]] = None
    ) -> 'BlobHashTree':
        """
        Build a blob hash tree from chunk hashes and headers.
        
        Args:
            chunk_hashes: List of chunk hashes
            headers: Optional headers dictionary
            
        Returns:
            Constructed BlobHashTree
        """
        if headers is None:
            headers = {}
        
        if not chunk_hashes:
            # To match rust, we have the hash of nothing
            hex_str = "8b8e620f084e48da0be2287fd12c5aaa4dbe14b468fd2e360f48d741fe7628a0"
            chunk_hashes = [YHash.from_hex(hex_str)]
        
        # Create leaf nodes for each chunk hash
        level = [
            TreeNode(hash=chunk_hash) 
            for chunk_hash in chunk_hashes
        ]
        
        # Build tree bottom-up
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else None
                
                parent_hash = await YHash.from_nodes(
                    left.hash,
                    right.hash if right else None
                )
                next_level.append(TreeNode(
                    hash=parent_hash,
                    left=left,
                    right=right
                ))
            level = next_level
        
        chunks_root = level[0]
        
        # If headers exist and have content, create combined tree
        if headers and any(headers.values()):
            metadata_root_hash = await YHash.from_headers(headers)
            metadata_root = TreeNode(hash=metadata_root_hash)
            
            combined_root_hash = await YHash.from_nodes(
                chunks_root.hash,
                metadata_root.hash
            )
            combined_root = TreeNode(
                hash=combined_root_hash,
                left=chunks_root,
                right=metadata_root
            )
            return cls(chunk_hashes, combined_root, headers)
        
        return cls(chunk_hashes, chunks_root, headers)
    
    def to_json(self) -> BlobHashTreeJSON:
        """Convert to JSON representation"""
        return BlobHashTreeJSON(
            tree_type=self.tree_type,
            chunk_hashes=[h.to_sha_string() for h in self.chunk_hashes],
            tree=node_to_json(self.tree),
            headers=self.headers
        )


@dataclass
class UploadChunkParams:
    """Parameters for uploading a single chunk"""
    blob_root_hash: YHash
    chunk_hash: YHash
    chunk_index: int
    chunk_data: bytes
    bucket_name: str
    owner: str
    project_id: str
    http_headers: Dict[str, str]


class StorageGatewayClient:
    """Client for interacting with the storage gateway"""
    
    def __init__(self, storage_gateway_url: str):
        """
        Initialize the storage gateway client.
        
        Args:
            storage_gateway_url: Base URL of the storage gateway
        """
        self.storage_gateway_url = storage_gateway_url.rstrip('/')
    
    def get_storage_gateway_url(self) -> str:
        """Get the storage gateway URL"""
        return self.storage_gateway_url
    
    async def upload_chunk(
        self, 
        params: UploadChunkParams,
        session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """
        Upload a single chunk to the storage gateway.
        
        Args:
            params: Upload parameters
            session: HTTP session
            
        Returns:
            Response from the server
            
        Raises:
            UploadError: If the upload fails
        """
        # Validate hash formats before sending to server
        blob_hash_string = params.blob_root_hash.to_sha_string()
        chunk_hash_string = params.chunk_hash.to_sha_string()
        
        validate_hash_format(
            blob_hash_string,
            f"upload_chunk[{params.chunk_index}] blob_hash"
        )
        validate_hash_format(
            chunk_hash_string,
            f"upload_chunk[{params.chunk_index}] chunk_hash"
        )
        
        async def _upload():
            # Use query parameters for metadata and raw bytes in body
            query_params = {
                'owner_id': params.owner,
                'blob_hash': blob_hash_string,
                'chunk_hash': chunk_hash_string,
                'chunk_index': str(params.chunk_index),
                'bucket_name': params.bucket_name,
                'project_id': params.project_id,
            }
            
            url = f"{self.storage_gateway_url}/{GATEWAY_VERSION}/chunk/"
            
            headers = {
                "Content-Type": "application/octet-stream",
                "X-Caffeine-Project-ID": params.project_id,
                **params.http_headers
            }
            
            async with session.put(
                url, 
                params=query_params,
                headers=headers,
                data=params.chunk_data
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    error = UploadError(
                        f"Failed to upload chunk {params.chunk_index}: "
                        f"{response.status} - {error_text}"
                    )
                    error.status = response.status
                    raise error
                
                result = await response.json()
                return {
                    'is_complete': result.get('status') == 'blob_complete'
                }
        
        return await with_retry(_upload)
    
    async def upload_blob_tree(
        self,
        blob_hash_tree: BlobHashTree,
        bucket_name: str,
        num_blob_bytes: int,
        owner: str,
        project_id: str,
        certificate_bytes: bytes,
        session: aiohttp.ClientSession
    ) -> None:
        """
        Upload the blob hash tree to the storage gateway.
        
        Args:
            blob_hash_tree: The blob hash tree
            bucket_name: Name of the bucket
            num_blob_bytes: Size of the blob in bytes
            owner: Owner ID
            project_id: Project ID
            certificate_bytes: Authentication certificate
            session: HTTP session
            
        Raises:
            UploadError: If the upload fails
        """
        # Validate all hashes in the tree before sending to server
        tree_json = blob_hash_tree.to_json()
        validate_hash_format(tree_json.tree.hash, "upload_blob_tree root hash")
        
        for idx, hash_str in enumerate(tree_json.chunk_hashes):
            validate_hash_format(hash_str, f"upload_blob_tree chunk_hash[{idx}]")
        
        async def _upload():
            url = f"{self.storage_gateway_url}/{GATEWAY_VERSION}/blob-tree/"
            
            # Convert tree_json to a serializable dict
            tree_dict = {
                'tree_type': tree_json.tree_type,
                'chunk_hashes': tree_json.chunk_hashes,
                'tree': {
                    'hash': tree_json.tree.hash,
                    'left': self._tree_node_to_dict(tree_json.tree.left),
                    'right': self._tree_node_to_dict(tree_json.tree.right)
                },
                'headers': tree_json.headers
            }
            
            request_body = {
                'blob_tree': tree_dict,
                'bucket_name': bucket_name,
                'num_blob_bytes': num_blob_bytes,
                'owner': owner,
                'project_id': project_id,
                'headers': blob_hash_tree.headers,
                'auth': {
                    'OwnerEgressSignature': list(certificate_bytes)
                }
            }
            
            headers = {
                "Content-Type": "application/json",
                "X-Caffeine-Project-ID": project_id
            }
            
            async with session.put(
                url,
                headers=headers,
                json=request_body
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    error = UploadError(
                        f"Failed to upload blob tree: {response.status} - {error_text}"
                    )
                    error.status = response.status
                    raise error
        
        return await with_retry(_upload)
    
    def _tree_node_to_dict(self, node: Optional[TreeNodeJSON]) -> Optional[Dict]:
        """Convert a TreeNodeJSON to a dictionary for JSON serialization"""
        if node is None:
            return None
        return {
            'hash': node.hash,
            'left': self._tree_node_to_dict(node.left),
            'right': self._tree_node_to_dict(node.right)
        }


class StorageClient:
    """
    Client for storing and retrieving files from the storage system.
    """
    
    def __init__(
        self,
        bucket: str,
        storage_gateway_url: str,
        backend_canister_id: str,
        project_id: str
    ):
        """
        Initialize the storage client.
        
        Args:
            bucket: Name of the bucket
            storage_gateway_url: URL of the storage gateway
            backend_canister_id: ID of the backend canister
            project_id: Project ID
        """
        self.bucket = bucket
        self.backend_canister_id = backend_canister_id
        self.project_id = project_id
        self.storage_gateway_client = StorageGatewayClient(storage_gateway_url)
    
    async def get_certificate(self, hash_str: str) -> bytes:
        """
        Get a certificate for a hash from the backend.
        
        Args:
            hash_str: Hash string
            
        Returns:
            Certificate bytes
            
        Raises:
            StorageError: If certificate retrieval fails
        """
        # This would call the backend canister to get a certificate
        # For now, return a mock certificate
        # In a real implementation, this would make a call to the ICP canister
        
        # Mock implementation
        return base64.b64decode("VGhpcyBpcyBhIG1vY2sgY2VydGlmaWNhdGUgZm9yICIgKyBoYXNoX3N0cg==")
    
    async def put_file(
        self,
        blob_bytes: bytes,
        content_type: str = "application/octet-stream",
        on_progress: Optional[Callable[[int], None]] = None
    ) -> Dict[str, str]:
        """
        Upload a file to the storage system.
        
        Args:
            blob_bytes: File bytes to upload
            content_type: MIME type of the file
            on_progress: Optional callback for upload progress (percentage)
            
        Returns:
            Dictionary with the file hash
        """
        # Create HTTP headers for fetch requests
        http_headers = {
            "Content-Type": content_type,
        }
        
        # File metadata headers that will be stored with the blob tree
        file_headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(blob_bytes)),
        }
        
        # Process the file for upload
        chunks, chunk_hashes, blob_hash_tree = await self._process_file_for_upload(
            blob_bytes, 
            file_headers
        )
        
        blob_root_hash = blob_hash_tree.tree.hash
        hash_string = blob_root_hash.to_sha_string()
        
        # Get certificate from backend
        certificate_bytes = await self.get_certificate(hash_string)
        
        # Upload the blob tree
        async with aiohttp.ClientSession() as session:
            await self.storage_gateway_client.upload_blob_tree(
                blob_hash_tree,
                self.bucket,
                len(blob_bytes),
                self.backend_canister_id,
                self.project_id,
                certificate_bytes,
                session
            )
            
            # Upload chunks in parallel
            await self._parallel_upload(
                chunks,
                chunk_hashes,
                blob_root_hash,
                http_headers,
                session,
                on_progress
            )
        
        return {"hash": hash_string}
    
    async def get_direct_url(self, hash_str: str) -> str:
        """
        Get a direct URL for downloading a file by its hash.
        
        Args:
            hash_str: File hash
            
        Returns:
            Download URL
            
        Raises:
            HashValidationError: If the hash format is invalid
        """
        if not hash_str:
            raise HashValidationError("Hash must not be empty")
        
        validate_hash_format(hash_str, f"get_direct_url for path '{hash_str}'")
        
        base_url = self.storage_gateway_client.get_storage_gateway_url()
        return (
            f"{base_url}/{GATEWAY_VERSION}/blob/"
            f"?blob_hash={hash_str}"
            f"&owner_id={self.backend_canister_id}"
            f"&project_id={self.project_id}"
        )
    
    async def _process_file_for_upload(
        self,
        file_bytes: bytes,
        headers: Dict[str, str]
    ) -> Tuple[List[bytes], List[YHash], BlobHashTree]:
        """
        Process a file for upload by splitting into chunks and computing hashes.
        
        Args:
            file_bytes: File bytes
            headers: File headers
            
        Returns:
            Tuple of (chunks, chunk_hashes, blob_hash_tree)
        """
        chunks = self._create_file_chunks(file_bytes)
        chunk_hashes = []
        
        for chunk in chunks:
            chunk_hash = await YHash.from_chunk(chunk)
            chunk_hashes.append(chunk_hash)
        
        blob_hash_tree = await BlobHashTree.build(chunk_hashes, headers)
        
        return chunks, chunk_hashes, blob_hash_tree
    
    async def _parallel_upload(
        self,
        chunks: List[bytes],
        chunk_hashes: List[YHash],
        blob_root_hash: YHash,
        http_headers: Dict[str, str],
        session: aiohttp.ClientSession,
        on_progress: Optional[Callable[[int], None]] = None
    ) -> None:
        """
        Upload chunks in parallel.
        
        Args:
            chunks: List of chunk bytes
            chunk_hashes: List of chunk hashes
            blob_root_hash: Root hash of the blob
            http_headers: HTTP headers for requests
            session: HTTP session
            on_progress: Progress callback
        """
        completed_chunks = 0
        total_chunks = len(chunks)
        
        async def upload_single_chunk(index: int):
            nonlocal completed_chunks
            
            chunk_data = chunks[index]
            chunk_hash = chunk_hashes[index]
            
            params = UploadChunkParams(
                blob_root_hash=blob_root_hash,
                chunk_hash=chunk_hash,
                chunk_index=index,
                chunk_data=chunk_data,
                bucket_name=self.bucket,
                owner=self.backend_canister_id,
                project_id=self.project_id,
                http_headers=http_headers
            )
            
            await self.storage_gateway_client.upload_chunk(params, session)
            
            # Update progress
            completed_chunks += 1
            if on_progress is not None:
                percentage = 100 if total_chunks == 0 else int((completed_chunks / total_chunks) * 100)
                on_progress(percentage)
        
        # Create tasks for parallel uploads
        tasks = []
        for worker_id in range(MAXIMUM_CONCURRENT_UPLOADS):
            for i in range(worker_id, len(chunks), MAXIMUM_CONCURRENT_UPLOADS):
                tasks.append(upload_single_chunk(i))
        
        await asyncio.gather(*tasks)
    
    def _create_file_chunks(self, file_bytes: bytes, chunk_size: int = 1024 * 1024) -> List[bytes]:
        """
        Split a file into chunks.
        
        Args:
            file_bytes: File bytes
            chunk_size: Size of each chunk in bytes
            
        Returns:
            List of chunk bytes
        """
        chunks = []
        total_size = len(file_bytes)
        num_chunks = math.ceil(total_size / chunk_size)
        
        for i in range(num_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, total_size)
            chunk = file_bytes[start:end]
            chunks.append(chunk)
        
        return chunks


# Example usage
async def example_usage():
    """Example of how to use the storage client"""
    # Initialize the client
    client = StorageClient(
        bucket="my-bucket",
        storage_gateway_url="https://storage.example.com",
        backend_canister_id="canister-123",
        project_id="project-456"
    )
    
    # Upload a file
    file_bytes = b"Hello, world!" * 1000
    
    def progress_callback(percentage):
        print(f"Upload progress: {percentage}%")
    
    result = await client.put_file(
        file_bytes,
        content_type="text/plain",
        on_progress=progress_callback
    )
    
    print(f"File uploaded with hash: {result['hash']}")
    
    # Get download URL
    url = await client.get_direct_url(result['hash'])
    print(f"Download URL: {url}")


# Run the example
if __name__ == "__main__":
    asyncio.run(example_usage())
