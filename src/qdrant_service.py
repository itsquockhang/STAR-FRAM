import os
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, UpdateStatus


class QdrantService:
    """
    A service class for interacting with Qdrant Vector Database.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        grpc_port: Optional[int] = None,
        prefer_grpc: Optional[bool] = None,
    ):
        # Resolve config from arguments or environment variables
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.grpc_port = grpc_port or int(os.getenv("QDRANT_GRPC_PORT", "6334"))
        
        prefer_grpc_env = os.getenv("QDRANT_PREFER_GRPC", "false").lower() == "true"
        self.prefer_grpc = prefer_grpc if prefer_grpc is not None else prefer_grpc_env

        print(f"Connecting to Qdrant at {self.host}:{self.port} (gRPC: {self.grpc_port}, prefer_grpc: {self.prefer_grpc})")
        self.client = QdrantClient(
            host=self.host,
            port=self.port,
            grpc_port=self.grpc_port,
            prefer_grpc=self.prefer_grpc,
        )

    def is_healthy(self) -> bool:
        """
        Check if the Qdrant service is responsive.
        """
        try:
            # We can use the cluster status check or a simple collection list to verify connection
            self.client.get_collections()
            return True
        except Exception as e:
            print(f"Health check failed: {e}")
            return False

    def list_collections(self) -> List[str]:
        """
        List all collection names in Qdrant.
        """
        response = self.client.get_collections()
        return [col.name for col in response.collections]

    def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Create a collection if it doesn't already exist.
        """
        existing = self.list_collections()
        if collection_name in existing:
            print(f"Collection '{collection_name}' already exists.")
            return True

        print(f"Creating collection '{collection_name}' (dim={vector_size}, distance={distance.name})...")
        try:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )
            return True
        except Exception as e:
            print(f"Failed to create collection '{collection_name}': {e}")
            return False

    def upsert_points(
        self,
        collection_name: str,
        points: List[Dict[str, Any]]
    ) -> bool:
        """
        Upsert a list of points into a collection.
        Each point dict should contain:
          - "id": int or str (UUID)
          - "vector": List[float]
          - "payload": Dict[str, Any] (optional)
        """
        qdrant_points = []
        for p in points:
            p_id = p.get("id")
            vector = p.get("vector")
            payload = p.get("payload", {})
            
            if p_id is None or vector is None:
                raise ValueError("Each point must have an 'id' and a 'vector'.")

            qdrant_points.append(
                PointStruct(id=p_id, vector=vector, payload=payload)
            )

        try:
            operation_info = self.client.upsert(
                collection_name=collection_name,
                wait=True,
                points=qdrant_points
            )
            return operation_info.status == UpdateStatus.COMPLETED
        except Exception as e:
            print(f"Failed to upsert points to collection '{collection_name}': {e}")
            return False

    def search_vectors(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        query_filter: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for nearest vectors.
        """
        try:
            response = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                query_filter=query_filter,
            )
            return [
                {
                    "id": res.id,
                    "score": res.score,
                    "payload": res.payload
                }
                for res in response.points
            ]
        except Exception as e:
            print(f"Search failed in collection '{collection_name}': {e}")
            return []

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.
        """
        try:
            self.client.delete_collection(collection_name=collection_name)
            print(f"Deleted collection '{collection_name}'.")
            return True
        except Exception as e:
            print(f"Failed to delete collection '{collection_name}': {e}")
            return False
