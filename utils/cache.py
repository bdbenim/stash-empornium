import logging

logger = logging.getLogger(__name__)
use_redis = False
try:
    import redis
    use_redis = True
except:
    logger.info("Redis module not found, using local caching only")

CHUNK_SIZE = 5000

class Cache:

    __items__: dict = {}
    __redis__ = None
    prefix: str = "stash-empornium"

    def __init__(self, redisHost: str|None=None, redisPort:int=6379, user: str|None=None, password: str|None=None, use_ssl:bool = False) -> None:
        if redisHost is not None and use_redis:
            self.__redis__ = redis.Redis(redisHost, redisPort, username=user, password=password, ssl=use_ssl, decode_responses=True)
            try:
                self.__redis__.exists("connectioncheck")
                logger.info(f"Successfully connected to redis at {redisHost}:{redisPort}{' using ssl' if use_ssl else ''}")
            except Exception as e:
                logger.error(f"Failed to connect to redis: {e}")
                self.__redis__ = None
        else:
            logger.debug("Not connecting to redis")

    def exists(self, key: str) -> bool:
        if key in self.__items__:
            return True
        return self.__redis__ is not None and self.__redis__.exists(f"{self.prefix}:{key}")

    def get(self, key: str) -> str|None:
        if key in self.__items__:
            return self.__items__[key]
        elif self.__redis__ is not None and self.__redis__.exists(f"{self.prefix}:{key}"):
            value = self.__redis__.get(f"{self.prefix}:{key}")
            self.__items__[key] = value
            return value
        return None

    def add(self, key, value) -> None:
        self.__items__[key] = value
        if self.__redis__ is not None:
            self.__redis__.set(f"{self.prefix}:{key}", value)
    
    def clear(self) -> None:
        lcount = len(self.__items__)
        self.__items__.clear()
        if self.__redis__ is not None:
            cursor = '0'
            ns_keys = f"{self.prefix}:*"
            count = 0
            while cursor != 0:
                cursor, keys = self.__redis__.scan(cursor=cursor, match=ns_keys, count=CHUNK_SIZE)
                if keys:
                    count += len(keys)
                    self.__redis__.delete(*keys)
            logger.debug(f"Cleared {lcount} local cache entries and {count} remote entries")