import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

logger = logging.getLogger("starfarm.database")

# DB Clients
mongo_client: AsyncIOMotorClient = None
db = None
redis_client: Redis = None

async def init_db():
    global mongo_client, db, redis_client
    
    # Configure MongoDB
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/starfarm")
    logger.info(f"Connecting to MongoDB at {mongo_uri}")
    try:
        mongo_client = AsyncIOMotorClient(mongo_uri)
        # Verify connection by running a command
        await mongo_client.admin.command('ping')
        
        # Get DB name from URI or default to 'starfarm'
        # e.g., mongodb://host:port/database_name
        db_name = "starfarm"
        if "/" in mongo_uri.replace("mongodb://", ""):
            parts = mongo_uri.split("/")
            if parts[-1]:
                db_name = parts[-1].split("?")[0]
        
        db = mongo_client[db_name]
        logger.info(f"MongoDB connected successfully to database: {db_name}")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise e

    # Configure Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    logger.info(f"Connecting to Redis at {redis_host}:{redis_port}")
    try:
        redis_client = Redis(host=redis_host, port=redis_port, decode_responses=True)
        # Verify connection
        await redis_client.ping()
        logger.info("Redis connected successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise e

async def close_db():
    global mongo_client, redis_client
    if mongo_client:
        mongo_client.close()
        logger.info("MongoDB connection closed.")
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed.")

def get_db():
    if db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db

def get_redis():
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_db() first.")
    return redis_client
