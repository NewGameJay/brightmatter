"""
MH1 Firebase Client
Thread-safe Firebase client with connection pooling for concurrent agent access.

Features:
- Connection pooling for efficient concurrent access
- Thread-safe operations using locks
- Retry logic with exponential backoff
- Comprehensive error handling
- Support for batch operations
"""

import json
import os
import time
import threading
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from contextlib import contextmanager
from functools import wraps
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Firebase Admin SDK imports (lazy loaded)
_firebase_admin = None
_firestore = None


def _ensure_firebase():
    """Lazy load Firebase Admin SDK."""
    global _firebase_admin, _firestore
    if _firebase_admin is None:
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            _firebase_admin = firebase_admin
            _firestore = firestore
        except ImportError:
            raise ImportError(
                "firebase-admin package is required. "
                "Install with: pip install firebase-admin"
            )
    return _firebase_admin, _firestore


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 0.5  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    retryable_exceptions: tuple = field(default_factory=lambda: (
        Exception,  # Will be refined when Firebase is loaded
    ))


@dataclass
class PoolConfig:
    """Configuration for connection pooling."""
    max_connections: int = 10
    connection_timeout: float = 30.0  # seconds
    idle_timeout: float = 300.0  # seconds


class FirebaseError(Exception):
    """Base exception for Firebase operations."""
    pass


class FirebaseConnectionError(FirebaseError):
    """Raised when connection to Firebase fails."""
    pass


class DocumentNotFoundError(FirebaseError):
    """Raised when a document is not found."""
    pass


class BatchWriteError(FirebaseError):
    """Raised when a batch write operation fails."""
    def __init__(self, message: str, failed_operations: List[Dict] = None):
        super().__init__(message)
        self.failed_operations = failed_operations or []


def retry_operation(retry_config: RetryConfig = None):
    """
    Decorator for retrying operations with exponential backoff.
    
    Args:
        retry_config: Configuration for retry behavior
    """
    if retry_config is None:
        retry_config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(retry_config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_config.retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < retry_config.max_retries:
                        delay = min(
                            retry_config.base_delay * (retry_config.exponential_base ** attempt),
                            retry_config.max_delay
                        )
                        logger.warning(
                            f"Operation {func.__name__} failed (attempt {attempt + 1}/"
                            f"{retry_config.max_retries + 1}), retrying in {delay:.2f}s: {e}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Operation {func.__name__} failed after "
                            f"{retry_config.max_retries + 1} attempts: {e}"
                        )
            
            raise last_exception
        return wrapper
    return decorator


class ConnectionPool:
    """
    Thread-safe connection pool for Firebase clients.
    
    Manages multiple Firebase app instances for concurrent access.
    """
    
    def __init__(self, config: PoolConfig = None):
        self.config = config or PoolConfig()
        self._lock = threading.RLock()
        self._connections: Dict[str, Any] = {}
        self._connection_times: Dict[str, datetime] = {}
        self._in_use: Dict[str, bool] = {}
        self._condition = threading.Condition(self._lock)
    
    def get_connection(self, project_id: str, credentials_path: str = None) -> Any:
        """
        Get a Firebase client from the pool.
        
        Thread-safe: Will wait if all connections are in use.
        """
        with self._condition:
            # Wait for an available connection if pool is full
            while self._count_in_use() >= self.config.max_connections:
                logger.debug(f"Connection pool full, waiting...")
                notified = self._condition.wait(timeout=self.config.connection_timeout)
                if not notified:
                    raise FirebaseConnectionError(
                        f"Timeout waiting for connection after {self.config.connection_timeout}s"
                    )
            
            # Find or create a connection
            conn_key = f"{project_id}_{threading.current_thread().ident}"
            
            if conn_key in self._connections and not self._in_use.get(conn_key, False):
                # Reuse existing idle connection
                self._in_use[conn_key] = True
                self._connection_times[conn_key] = datetime.now(timezone.utc)
                return self._connections[conn_key]
            
            # Create new connection
            client = self._create_connection(project_id, credentials_path)
            self._connections[conn_key] = client
            self._in_use[conn_key] = True
            self._connection_times[conn_key] = datetime.now(timezone.utc)
            
            return client
    
    def release_connection(self, project_id: str):
        """Release a connection back to the pool."""
        with self._condition:
            conn_key = f"{project_id}_{threading.current_thread().ident}"
            if conn_key in self._in_use:
                self._in_use[conn_key] = False
            self._condition.notify_all()
    
    def _count_in_use(self) -> int:
        """Count connections currently in use."""
        return sum(1 for in_use in self._in_use.values() if in_use)
    
    def _create_connection(self, project_id: str, credentials_path: str = None) -> Any:
        """Create a new Firebase connection."""
        firebase_admin, firestore = _ensure_firebase()
        
        # Check if app already exists
        app_name = f"mh1_{project_id}_{threading.current_thread().ident}"
        
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            # App doesn't exist, create it
            if credentials_path:
                cred = firebase_admin.credentials.Certificate(credentials_path)
            else:
                # Credential resolution order:
                #   1. FIREBASE_SERVICE_ACCOUNT_JSON  (canonical)
                #   2. FIREBASE_CREDENTIALS_JSON      (alias — used by MCP/Modal)
                #   3. SERVICE_ACCOUNT_KEY             (legacy alias)
                #   4. GOOGLE_APPLICATION_CREDENTIALS  (file path)
                #   5. Application Default Credentials
                sa_json = (
                    os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
                    or os.environ.get("FIREBASE_CREDENTIALS_JSON")
                    or os.environ.get("SERVICE_ACCOUNT_KEY")
                )
                cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                sa_key_path = os.environ.get("SERVICE_ACCOUNT_KEY_PATH", "")
                if sa_json and isinstance(sa_json, str) and sa_json.strip().startswith("{"):
                    cred = firebase_admin.credentials.Certificate(json.loads(sa_json))
                elif sa_json and isinstance(sa_json, str) and os.path.isfile(sa_json):
                    cred = firebase_admin.credentials.Certificate(sa_json)
                elif sa_key_path and os.path.isfile(sa_key_path):
                    cred = firebase_admin.credentials.Certificate(sa_key_path)
                elif cred_path and os.path.isfile(cred_path):
                    cred = firebase_admin.credentials.Certificate(cred_path)
                else:
                    # Clear GOOGLE_APPLICATION_CREDENTIALS if it points to a nonexistent file
                    # to prevent google.auth.default() from failing on stale paths
                    if cred_path and not os.path.isfile(cred_path):
                        logger.warning(
                            f"GOOGLE_APPLICATION_CREDENTIALS points to nonexistent file: {cred_path}. "
                            f"Clearing for ADC fallback."
                        )
                        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
                    cred = firebase_admin.credentials.ApplicationDefault()
            
            options = {"projectId": project_id}
            storage_bucket = os.environ.get(
                "FIREBASE_STORAGE_BUCKET",
                "moe-platform-479917.firebasestorage.app",
            )
            if storage_bucket:
                options["storageBucket"] = storage_bucket
            app = firebase_admin.initialize_app(cred, options, name=app_name)
        
        return firestore.client(app)
    
    def cleanup_idle(self):
        """Remove idle connections that have exceeded the timeout."""
        with self._lock:
            now = datetime.now(timezone.utc)
            keys_to_remove = []
            
            for conn_key, last_used in self._connection_times.items():
                if not self._in_use.get(conn_key, False):
                    idle_time = (now - last_used).total_seconds()
                    if idle_time > self.config.idle_timeout:
                        keys_to_remove.append(conn_key)
            
            for key in keys_to_remove:
                del self._connections[key]
                del self._connection_times[key]
                self._in_use.pop(key, None)
                logger.debug(f"Removed idle connection: {key}")
    
    def close_all(self):
        """Close all connections in the pool."""
        with self._lock:
            firebase_admin, _ = _ensure_firebase()
            
            for conn_key in list(self._connections.keys()):
                try:
                    app_name = f"mh1_{conn_key.split('_')[0]}_{conn_key.split('_')[1]}"
                    app = firebase_admin.get_app(app_name)
                    firebase_admin.delete_app(app)
                except Exception as e:
                    logger.warning(f"Error closing connection {conn_key}: {e}")
            
            self._connections.clear()
            self._connection_times.clear()
            self._in_use.clear()


# Global connection pool
_connection_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def get_connection_pool() -> ConnectionPool:
    """Get or create the global connection pool."""
    global _connection_pool
    
    with _pool_lock:
        if _connection_pool is None:
            _connection_pool = ConnectionPool()
        return _connection_pool


class FirebaseClient:
    """
    Thread-safe Firebase Firestore client with connection pooling.
    
    Usage:
        client = FirebaseClient(project_id="my-project")
        
        # Get a document
        doc = client.get_document("users", "user123")
        
        # Query a collection
        results = client.query("users", [("status", "==", "active")])
        
        # Batch write
        operations = [
            {"type": "set", "collection": "users", "doc_id": "user1", "data": {...}},
            {"type": "update", "collection": "users", "doc_id": "user2", "data": {...}},
        ]
        client.batch_write(operations)
    """
    
    def __init__(
        self,
        project_id: str,
        credentials_path: str = None,
        retry_config: RetryConfig = None,
        pool_config: PoolConfig = None
    ):
        """
        Initialize Firebase client.
        
        Args:
            project_id: Firebase/GCP project ID
            credentials_path: Path to service account JSON file (optional)
            retry_config: Configuration for retry behavior
            pool_config: Configuration for connection pooling
        """
        self.project_id = project_id
        self.credentials_path = credentials_path
        self.retry_config = retry_config or RetryConfig()
        
        # Initialize pool with custom config if provided
        if pool_config:
            global _connection_pool
            with _pool_lock:
                _connection_pool = ConnectionPool(pool_config)
        
        self._local = threading.local()
        self._project_id = project_id
    
    @property
    def db(self):
        """
        Raw Firestore client for direct SDK operations.
        
        Use this when you need native Firestore API access without the
        FirebaseClient wrapper (e.g. when migrating code that already uses
        raw db.collection().document() patterns).
        
        The returned client is from the connection pool and should NOT be
        manually closed. It is thread-safe via the pool's per-thread keying.
        
        Unlike _get_client(), this immediately releases the pool slot so
        long-lived references (cached in module globals) don't exhaust the pool.
        """
        pool = get_connection_pool()
        client = pool.get_connection(self.project_id, self.credentials_path)
        pool.release_connection(self.project_id)
        return client
    
    @contextmanager
    def _get_client(self):
        """Context manager for getting a pooled client."""
        pool = get_connection_pool()
        client = pool.get_connection(self.project_id, self.credentials_path)
        try:
            yield client
        finally:
            pool.release_connection(self.project_id)
    
    def resolve_collection_path(self, path: str):
        """
        Resolve a slash-separated path into a Firestore collection reference.

        Firestore paths alternate collection/document segments. The path must
        have an odd number of segments (ending in a collection).

        Example:
            resolve_collection_path("system/intelligence/episodic/tenant/skill")
            -> collection("system").document("intelligence")
               .collection("episodic").document("tenant").collection("skill")

        Note: The Firestore Python SDK's client.collection() handles slash
        paths natively, so this is equivalent to client.collection(path).
        This method exists for explicit validation and self-documenting code.
        """
        parts = path.strip("/").split("/")
        if len(parts) % 2 == 0:
            raise ValueError(
                f"Firestore collection path must have odd number of segments "
                f"(collection/doc/collection/...), got {len(parts)}: {path}"
            )
        with self._get_client() as client:
            ref = client
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    ref = ref.collection(part)
                else:
                    ref = ref.document(part)
            return ref

    def list_subcollections(self, document_path: str) -> List[str]:
        """
        List subcollection IDs under a document.

        Args:
            document_path: Even-segment slash path to a document,
                           e.g. "system/intelligence/episodic/tenant123"

        Returns:
            List of subcollection IDs (not full paths)
        """
        parts = document_path.strip("/").split("/")
        if len(parts) % 2 != 0:
            raise ValueError(
                f"Document path must have even number of segments, got {len(parts)}: {document_path}"
            )
        with self._get_client() as client:
            ref = client
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    ref = ref.collection(part)
                else:
                    ref = ref.document(part)
            return [col.id for col in ref.collections()]

    @retry_operation()
    def get_document(
        self,
        collection: str,
        doc_id: str,
        subcollection: str = None,
        subdoc_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single document by ID.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            subcollection: Optional subcollection name
            subdoc_id: Optional subdocument ID
        
        Returns:
            Document data as dict, or None if not found
        """
        with self._get_client() as client:
            ref = client.collection(collection).document(doc_id)
            
            if subcollection and subdoc_id:
                ref = ref.collection(subcollection).document(subdoc_id)
            
            doc = ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data["_id"] = doc.id
                data["_path"] = doc.reference.path
                return data
            
            return None
    
    @retry_operation()
    def get_collection(
        self,
        collection: str,
        parent_doc: str = None,
        parent_collection: str = None,
        limit: int = None,
        order_by: str = None,
        order_direction: str = "ASCENDING"
    ) -> List[Dict[str, Any]]:
        """
        Get all documents in a collection.
        
        Args:
            collection: Collection name
            parent_doc: Parent document ID (for subcollections)
            parent_collection: Parent collection name (for subcollections)
            limit: Maximum number of documents to return
            order_by: Field to order by
            order_direction: "ASCENDING" or "DESCENDING"
        
        Returns:
            List of document data dicts
        """
        with self._get_client() as client:
            if parent_collection and parent_doc:
                ref = client.collection(parent_collection).document(parent_doc).collection(collection)
            else:
                ref = client.collection(collection)
            
            query = ref
            
            if order_by:
                _, firestore = _ensure_firebase()
                direction = (
                    firestore.Query.DESCENDING 
                    if order_direction.upper() == "DESCENDING" 
                    else firestore.Query.ASCENDING
                )
                query = query.order_by(order_by, direction=direction)
            
            if limit:
                query = query.limit(limit)
            
            docs = query.stream()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["_id"] = doc.id
                data["_path"] = doc.reference.path
                results.append(data)
            
            return results
    
    @retry_operation()
    def set_document(
        self,
        collection: str,
        doc_id: str,
        data: Dict[str, Any],
        merge: bool = False,
        subcollection: str = None,
        subdoc_id: str = None
    ) -> str:
        """
        Set (create or overwrite) a document.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            data: Document data
            merge: If True, merge with existing data; if False, overwrite
            subcollection: Optional subcollection name
            subdoc_id: Optional subdocument ID
        
        Returns:
            Document ID
        """
        with self._get_client() as client:
            ref = client.collection(collection).document(doc_id)
            
            if subcollection and subdoc_id:
                ref = ref.collection(subcollection).document(subdoc_id)
            
            # Add metadata
            data_with_meta = {
                **data,
                "_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            if not merge:
                data_with_meta["_created_at"] = data.get(
                    "_created_at", 
                    datetime.now(timezone.utc).isoformat()
                )
            
            ref.set(data_with_meta, merge=merge)
            
            logger.debug(f"Set document: {ref.path}")
            return doc_id
    
    @retry_operation()
    def add_document(
        self,
        collection: str,
        data: Dict[str, Any],
        parent_doc: str = None,
        parent_collection: str = None
    ) -> str:
        """
        Add a new document with auto-generated ID.
        
        Args:
            collection: Collection name
            data: Document data
            parent_doc: Parent document ID (for subcollections)
            parent_collection: Parent collection name (for subcollections)
        
        Returns:
            Generated document ID
        """
        with self._get_client() as client:
            if parent_collection and parent_doc:
                ref = client.collection(parent_collection).document(parent_doc).collection(collection)
            else:
                ref = client.collection(collection)
            
            # Add metadata
            now = datetime.now(timezone.utc).isoformat()
            data_with_meta = {
                **data,
                "_created_at": now,
                "_updated_at": now,
            }
            
            _, doc_ref = ref.add(data_with_meta)
            
            logger.debug(f"Added document: {doc_ref.path}")
            return doc_ref.id
    
    @retry_operation()
    def update_document(
        self,
        collection: str,
        doc_id: str,
        data: Dict[str, Any],
        subcollection: str = None,
        subdoc_id: str = None
    ) -> str:
        """
        Update specific fields in a document.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            data: Fields to update
            subcollection: Optional subcollection name
            subdoc_id: Optional subdocument ID
        
        Returns:
            Document ID
        
        Raises:
            DocumentNotFoundError: If document doesn't exist
        """
        with self._get_client() as client:
            ref = client.collection(collection).document(doc_id)
            
            if subcollection and subdoc_id:
                ref = ref.collection(subcollection).document(subdoc_id)
            
            # Check if document exists
            if not ref.get().exists:
                raise DocumentNotFoundError(
                    f"Document not found: {collection}/{doc_id}"
                )
            
            # Add update timestamp
            data_with_meta = {
                **data,
                "_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            ref.update(data_with_meta)
            
            logger.debug(f"Updated document: {ref.path}")
            return doc_id
    
    @retry_operation()
    def delete_document(
        self,
        collection: str,
        doc_id: str,
        subcollection: str = None,
        subdoc_id: str = None
    ) -> bool:
        """
        Delete a document.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            subcollection: Optional subcollection name
            subdoc_id: Optional subdocument ID
        
        Returns:
            True if deleted successfully
        """
        with self._get_client() as client:
            ref = client.collection(collection).document(doc_id)
            
            if subcollection and subdoc_id:
                ref = ref.collection(subcollection).document(subdoc_id)
            
            ref.delete()
            
            logger.debug(f"Deleted document: {ref.path}")
            return True
    
    @retry_operation()
    def query(
        self,
        collection: str,
        filters: List[tuple],
        limit: int = None,
        order_by: str = None,
        order_direction: str = "ASCENDING",
        parent_doc: str = None,
        parent_collection: str = None
    ) -> List[Dict[str, Any]]:
        """
        Query documents with filters.
        
        Args:
            collection: Collection name
            filters: List of filter tuples (field, operator, value)
                Operators: ==, !=, <, <=, >, >=, in, not-in, array-contains, array-contains-any
            limit: Maximum number of documents
            order_by: Field to order by
            order_direction: "ASCENDING" or "DESCENDING"
            parent_doc: Parent document ID (for subcollections)
            parent_collection: Parent collection name (for subcollections)
        
        Returns:
            List of matching document data dicts
        """
        with self._get_client() as client:
            if parent_collection and parent_doc:
                ref = client.collection(parent_collection).document(parent_doc).collection(collection)
            else:
                ref = client.collection(collection)
            
            query = ref
            
            # Apply filters
            for field, operator, value in filters:
                query = query.where(field, operator, value)
            
            # Apply ordering
            if order_by:
                _, firestore = _ensure_firebase()
                direction = (
                    firestore.Query.DESCENDING 
                    if order_direction.upper() == "DESCENDING" 
                    else firestore.Query.ASCENDING
                )
                query = query.order_by(order_by, direction=direction)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Execute query
            docs = query.stream()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["_id"] = doc.id
                data["_path"] = doc.reference.path
                results.append(data)
            
            return results
    
    def batch_write(
        self,
        operations: List[Dict[str, Any]],
        atomic: bool = True
    ) -> Dict[str, Any]:
        """
        Execute multiple write operations in a batch.
        
        Args:
            operations: List of operation dicts with keys:
                - type: "set", "update", or "delete"
                - collection: Collection name
                - doc_id: Document ID (optional for "add" type)
                - data: Document data (for set/update)
                - merge: Boolean (for set operations)
            atomic: If True, all operations succeed or fail together
        
        Returns:
            Dict with:
                - success: bool
                - operations_count: int
                - failed_operations: List of failed ops (if not atomic)
        
        Raises:
            BatchWriteError: If atomic batch fails
        """
        if not operations:
            return {"success": True, "operations_count": 0, "failed_operations": []}
        
        with self._get_client() as client:
            batch = client.batch()
            failed_operations = []
            
            for i, op in enumerate(operations):
                try:
                    op_type = op.get("type", "set")
                    collection = op["collection"]
                    doc_id = op.get("doc_id")
                    data = op.get("data", {})
                    merge = op.get("merge", False)
                    
                    if doc_id:
                        ref = client.collection(collection).document(doc_id)
                    else:
                        ref = client.collection(collection).document()
                    
                    if op_type == "set":
                        now = datetime.now(timezone.utc).isoformat()
                        data_with_meta = {
                            **data,
                            "_updated_at": now,
                        }
                        if not merge:
                            data_with_meta["_created_at"] = data.get("_created_at", now)
                        batch.set(ref, data_with_meta, merge=merge)
                    
                    elif op_type == "update":
                        data_with_meta = {
                            **data,
                            "_updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        batch.update(ref, data_with_meta)
                    
                    elif op_type == "delete":
                        batch.delete(ref)
                    
                    else:
                        raise ValueError(f"Unknown operation type: {op_type}")
                
                except Exception as e:
                    if atomic:
                        raise BatchWriteError(
                            f"Batch operation {i} failed: {e}",
                            failed_operations=[{**op, "error": str(e)}]
                        )
                    else:
                        failed_operations.append({**op, "error": str(e), "index": i})
            
            # Commit the batch
            try:
                batch.commit()
                logger.info(f"Batch write completed: {len(operations)} operations")
            except Exception as e:
                if atomic:
                    raise BatchWriteError(f"Batch commit failed: {e}")
                else:
                    # Mark all operations as failed
                    failed_operations = [
                        {**op, "error": str(e), "index": i}
                        for i, op in enumerate(operations)
                    ]
            
            return {
                "success": len(failed_operations) == 0,
                "operations_count": len(operations),
                "failed_operations": failed_operations
            }
    
    def transaction(self, callback: Callable) -> Any:
        """
        Execute operations in a transaction.

        Args:
            callback: Function that takes a transaction object
                and the Firestore client, and returns a result.
                The function will be retried if there's a contention.

        Returns:
            Result from the callback

        Example:
            def my_update(transaction, client):
                ref = client.collection('items').document('item1')
                snapshot = ref.get(transaction=transaction)
                new_val = snapshot.get('count') + 1
                transaction.update(ref, {'count': new_val})
                return new_val

            result = firebase_client.transaction(my_update)
        """
        firebase_admin, firestore = _ensure_firebase()

        with self._get_client() as client:
            @firestore.transactional
            def run_transaction(transaction):
                return callback(transaction, client)

            transaction_ref = client.transaction()
            return run_transaction(transaction_ref)
    
    def get_storage_bucket(self):
        """Get a Firebase Storage bucket handle for file uploads/downloads."""
        firebase_admin, _ = _ensure_firebase()
        from firebase_admin import storage as _fb_storage

        pool = get_connection_pool()
        app_name = f"mh1_{self.project_id}_{threading.current_thread().ident}"
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            pool.get_connection(self.project_id, self.credentials_path)
            pool.release_connection(self.project_id)
            app = firebase_admin.get_app(app_name)

        bucket_name = os.environ.get(
            "FIREBASE_STORAGE_BUCKET",
            "moe-platform-479917.firebasestorage.app",
        )
        return _fb_storage.bucket(bucket_name, app=app)

    def close(self):
        """Close all connections in the pool."""
        pool = get_connection_pool()
        pool.close_all()


# Singleton client accessor
_default_client: Optional[FirebaseClient] = None
_client_lock = threading.Lock()


def get_firebase_client(
    project_id: str = None,
    credentials_path: str = None
) -> FirebaseClient:
    """
    Get or create a Firebase client.
    
    Uses environment variables if project_id not provided:
    - FIREBASE_PROJECT_ID or GCP_PROJECT_ID
    - GOOGLE_APPLICATION_CREDENTIALS for credentials
    
    Args:
        project_id: Firebase/GCP project ID
        credentials_path: Path to service account JSON
    
    Returns:
        FirebaseClient instance
    """
    global _default_client
    
    # Resolve project ID
    if not project_id:
        project_id = os.environ.get(
            "FIREBASE_PROJECT_ID",
            os.environ.get("GCP_PROJECT_ID")
        )
    
    # Fallback: extract project_id from service account JSON
    if not project_id:
        sa_json = (
            os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
            or os.environ.get("FIREBASE_CREDENTIALS_JSON")
            or os.environ.get("SERVICE_ACCOUNT_KEY")
        )
        if sa_json:
            try:
                sa_data = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
                project_id = sa_data.get("project_id")
            except (json.JSONDecodeError, AttributeError):
                pass
    
    if not project_id:
        raise ValueError(
            "project_id required. Set FIREBASE_PROJECT_ID or GCP_PROJECT_ID environment variable."
        )
    
    with _client_lock:
        if _default_client is None or _default_client.project_id != project_id:
            _default_client = FirebaseClient(project_id, credentials_path)
        return _default_client


if __name__ == "__main__":
    # Example usage and basic test
    print("Firebase Client Module")
    print("=" * 50)
    print("This module provides thread-safe Firebase Firestore access.")
    print("\nUsage:")
    print("  from lib.firebase_client import get_firebase_client, FirebaseClient")
    print('  client = get_firebase_client(project_id="my-project")')
    print('  doc = client.get_document("users", "user123")')
    print("\nEnvironment variables:")
    print("  FIREBASE_PROJECT_ID - Firebase project ID")
    print("  GOOGLE_APPLICATION_CREDENTIALS - Path to service account JSON")
