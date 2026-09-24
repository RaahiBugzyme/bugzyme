import redis.asyncio as redis


class RedisClient:

    def __init__(self):
        self.redis = redis.Redis(
            host="localhost",
            port=6379,
            decode_responses=True
        )

    async def ping(self):
        return await self.redis.ping()

    async def set_value(self, key, value):
        await self.redis.set(key, value, ex=5)

    async def get_value(self, key):
        return await self.redis.get(key)

    async def set_hash(self, key, field, value):
        await self.redis.hset(key, field, value)

    async def get_hash(self, key, field):
        return await self.redis.hget(key, field)

    async def set_with_expiry(self, key, value, seconds):
        await self.redis.set(
            key,
            value,
            ex=seconds
        )